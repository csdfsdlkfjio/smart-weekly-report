"""演示数据（M7）测试：规模、埋点数据、幂等性与登录联调。"""

from datetime import date, datetime

from sqlalchemy import func, select

from app import models
from app.seed import DEMO_PASSWORD, reset_all_data, seed_demo_data


def test_seed_dataset_and_idempotency(session_factory):
    db = session_factory()
    try:
        first = seed_demo_data(db)
        second = seed_demo_data(db)

        assert first["created"]["users"] == 8
        assert first["created"]["weeks"] == 3
        assert first["created"]["member_reports"] == 9
        assert first["created"]["versions"] == 9
        assert first["created"]["audit_logs"] == 9
        assert second["created"] == {
            "departments": 0,
            "users": 0,
            "weeks": 0,
            "member_reports": 0,
            "versions": 0,
            "audit_logs": 0,
        }

        department = db.scalar(
            select(models.Department).where(models.Department.name == "心内科")
        )
        members = list(
            db.scalars(
                select(models.User).where(
                    models.User.dept_id == department.id,
                    models.User.role == "member",
                )
            )
        )
        assert len(members) == 5

        weeks = list(db.scalars(select(models.Week).order_by(models.Week.week_no)))
        assert [week.week_no for week in weeks] == [1, 2, 3]
        week1, week2, week3 = weeks

        # 周次必须是周一至周日
        assert week1.start_date == date(2026, 10, 19)
        assert week1.end_date == date(2026, 10, 25)
        assert week1.start_date.weekday() == 0
        assert week1.end_date.weekday() == 6

        assert week2.start_date == date(2026, 10, 26)
        assert week2.end_date == date(2026, 11, 1)
        assert week2.start_date.weekday() == 0
        assert week2.end_date.weekday() == 6

        # 第 3 周为空白周，不预置任何成员报告
        assert week3.start_date == date(2026, 11, 2)
        assert week3.end_date == date(2026, 11, 8)
        assert week3.start_date.weekday() == 0
        assert week3.end_date.weekday() == 6
        assert (
            db.scalar(
                select(func.count())
                .select_from(models.MemberReport)
                .where(models.MemberReport.week_id == week3.id)
            )
            == 0
        )

        week1_reports = list(
            db.scalars(select(models.MemberReport).where(models.MemberReport.week_id == week1.id))
        )
        assert len(week1_reports) == 5
        assert all(report.status == "已提交" for report in week1_reports)
        assert all(
            report.submitted_at == datetime(2026, 10, 25, 18, 0) for report in week1_reports
        )

        week2_reports = list(
            db.scalars(select(models.MemberReport).where(models.MemberReport.week_id == week2.id))
        )
        assert len(week2_reports) == 4

        users = {user.username: user for user in members}
        member_d_week2 = db.scalar(
            select(models.MemberReport).where(
                models.MemberReport.user_id == users["member_d"].id,
                models.MemberReport.week_id == week2.id,
            )
        )
        assert member_d_week2 is None, "member_d 第 2 周应未提交"

        reports = {report.user_id: report for report in week1_reports}
        user_ids = {user.username: user.id for user in members}

        assert "完成护理质控检查" in reports[user_ids["member_a"]].done_items
        assert "护理质控自查已完成" in reports[user_ids["member_b"]].done_items
        assert "日常工作正常开展" in reports[user_ids["member_c"]].done_items
        assert "继续推进相关工作" in reports[user_ids["member_c"]].done_items

        # A4：协调事项跨两周存在且未出现在完成事项
        week2_by_user = {report.user_id: report for report in week2_reports}
        a_week1 = reports[user_ids["member_a"]]
        a_week2 = week2_by_user[user_ids["member_a"]]
        assert "协调设备科维修监护仪" in a_week1.coord_items
        assert "协调设备科维修监护仪" in a_week2.coord_items
        assert "协调设备科维修监护仪" not in a_week1.done_items
        assert "协调设备科维修监护仪" not in a_week2.done_items

        e_week1 = reports[user_ids["member_e"]]
        e_week2 = week2_by_user[user_ids["member_e"]]
        assert "推进电子病历优化" in e_week1.plan_items
        assert "推进电子病历优化" in e_week2.plan_items
        assert "推进电子病历优化" not in e_week1.done_items
        assert "推进电子病历优化" not in e_week2.done_items

        assert db.scalar(select(func.count()).select_from(models.ReportVersion)) == 9
        assert (
            db.scalar(
                select(func.count())
                .select_from(models.AuditLog)
                .where(models.AuditLog.action == "submit")
            )
            == 9
        )
    finally:
        db.close()


def test_reset_then_reseed_restores_correct_week_dates(session_factory):
    db = session_factory()
    try:
        seed_demo_data(db)
        reset_all_data(db)

        assert db.scalar(select(func.count()).select_from(models.User)) == 0
        assert db.scalar(select(func.count()).select_from(models.Week)) == 0
        assert db.scalar(select(func.count()).select_from(models.MemberReport)) == 0

        seed_demo_data(db)
        weeks = list(db.scalars(select(models.Week).order_by(models.Week.week_no)))
        assert [(week.start_date, week.end_date) for week in weeks] == [
            (date(2026, 10, 19), date(2026, 10, 25)),
            (date(2026, 10, 26), date(2026, 11, 1)),
            (date(2026, 11, 2), date(2026, 11, 8)),
        ]
    finally:
        db.close()


def test_seeded_member_a_can_login_and_read_week1(client, session_factory, login):
    result = seed_demo_data(session_factory())

    headers = login("member_a", DEMO_PASSWORD)
    response = client.get(
        "/api/member/report",
        params={"week_id": result["week_ids"][1]},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    report = response.json()
    assert report is not None
    assert report["status"] == "已提交"
    assert report["version"] == 1
    assert "完成护理质控检查" in report["done"]

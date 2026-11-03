"""演示数据（M7）测试：规模、埋点数据、幂等性与登录联调。"""

from sqlalchemy import func, select

from app import models
from app.seed import DEMO_PASSWORD, seed_demo_data


def test_seed_dataset_and_idempotency(session_factory):
    db = session_factory()
    try:
        first = seed_demo_data(db)
        second = seed_demo_data(db)

        assert first["created"]["users"] == 8
        assert first["created"]["weeks"] == 2
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
        assert [week.week_no for week in weeks] == [1, 2]
        week1, week2 = weeks

        week1_reports = list(
            db.scalars(select(models.MemberReport).where(models.MemberReport.week_id == week1.id))
        )
        assert len(week1_reports) == 5
        assert all(report.status == "已提交" for report in week1_reports)

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

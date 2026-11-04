"""演示数据种子：幂等，可重复执行。

用法：
    python -m app.seed            # 幂等灌入，已有数据不重复插入
    python -m app.seed --reset    # 先清空全部表，再重新灌入

也可随应用启动自动执行（见 app/main.py 的 lifespan）。

演示数据设计：
- 1 个科室（心内科）、5 名成员、连续 2 周 + 第 3 周空白周
- 第 1 周 5 人全部已提交；第 2 周 4 人已提交，member_d 故意未提交
- 第 3 周（2026-11-02 ~ 2026-11-08）不预置任何报告，用于空白填报演示
- member_a / member_b 写入近义重复的护理质控表述（验证 A1 归并）
- member_c 写入空泛表述（验证 A3 校验）
- member_a 的“协调设备科维修监护仪”连续两周存在且未完成（验证 A4 风险提示）
- member_e 的“推进电子病历优化”连续两周停留在计划中（验证 A4 连续未推进）
"""

from __future__ import annotations

import sys
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth, models
from app.db import Base, SessionLocal, init_db

DEPT_NAME = "心内科"
DEMO_PASSWORD = "demo123"

# (username, name, role, 是否属于上述科室)
DEMO_USERS: tuple[tuple[str, str, str, bool], ...] = (
    ("member_a", "张医生", models.Role.MEMBER.value, True),
    ("member_b", "李医生", models.Role.MEMBER.value, True),
    ("member_c", "王医生", models.Role.MEMBER.value, True),
    ("member_d", "赵医生", models.Role.MEMBER.value, True),
    ("member_e", "陈医生", models.Role.MEMBER.value, True),
    ("director", "王主任", models.Role.DIRECTOR.value, True),
    ("leader", "院领导", models.Role.LEADER.value, False),
    ("admin", "系统管理员", models.Role.ADMIN.value, False),
)

DEMO_WEEKS: tuple[dict[str, Any], ...] = (
    {
        "week_no": 1,
        "start_date": date(2026, 10, 19),
        "end_date": date(2026, 10, 25),
        "deadline": datetime(2026, 10, 27, 23, 59),
    },
    {
        "week_no": 2,
        "start_date": date(2026, 10, 26),
        "end_date": date(2026, 11, 1),
        "deadline": datetime(2026, 11, 3, 23, 59),
    },
    {
        # 空白周：用于演示从零填报
        "week_no": 3,
        "start_date": date(2026, 11, 2),
        "end_date": date(2026, 11, 8),
        "deadline": datetime(2026, 11, 10, 23, 59),
    },
)

# 周次 -> 成员 -> 四类条目；未列出的成员表示未提交（member_d 第 2 周）
DEMO_REPORTS: dict[int, dict[str, dict[str, list[str]]]] = {
    1: {
        "member_a": {
            "done": ["完成护理质控检查", "组织科室业务学习 2 次"],
            "plan": ["开展护理技能培训"],
            "issue": ["部分病房设备老化"],
            "coord": ["协调设备科维修监护仪"],
        },
        "member_b": {
            "done": ["护理质控自查已完成", "整理出院病历 30 份"],
            "plan": ["优化排班流程"],
            "issue": ["护理人力紧张"],
            "coord": [],
        },
        "member_c": {
            "done": ["日常工作正常开展", "继续推进相关工作"],
            "plan": ["继续推进相关工作"],
            "issue": [],
            "coord": [],
        },
        "member_d": {
            "done": ["完成院感专项检查", "参加院级质控会议"],
            "plan": ["开展院感培训"],
            "issue": ["院感培训场地不足"],
            "coord": ["协调会议室使用"],
        },
        "member_e": {
            "done": ["完成药品盘点", "更新护理文书模板"],
            "plan": ["推进电子病历优化"],
            "issue": [],
            "coord": ["协调信息科接口改造"],
        },
    },
    2: {
        "member_a": {
            "done": ["完成护理质控抽查 3 次", "组织科室业务学习 1 次"],
            "plan": ["开展护理技能培训"],
            "issue": [],
            # 连续两周出现、尚未闭环的协调事项（A4）
            "coord": ["协调设备科维修监护仪"],
        },
        "member_b": {
            "done": ["护理质控自查已完成", "完成出院病历归档"],
            "plan": ["优化排班流程"],
            "issue": ["护理人力紧张"],
            "coord": [],
        },
        "member_c": {
            "done": ["日常工作正常开展", "继续推进相关工作"],
            "plan": ["继续推进相关工作"],
            "issue": [],
            "coord": [],
        },
        "member_e": {
            "done": ["完成药品盘点"],
            # 连续两周停留在计划中、未出现在完成事项（A4）
            "plan": ["推进电子病历优化"],
            "issue": [],
            "coord": ["协调信息科接口改造"],
        },
        # member_d 第 2 周故意未提交
    },
}


def _snapshot(report: models.MemberReport) -> dict[str, Any]:
    return {
        "status": report.status,
        "version": report.version,
        "done": list(report.done_items or []),
        "plan": list(report.plan_items or []),
        "issue": list(report.issue_items or []),
        "coord": list(report.coord_items or []),
    }


def _seed(db: Session) -> dict[str, Any]:
    created = {
        "departments": 0,
        "users": 0,
        "weeks": 0,
        "member_reports": 0,
        "versions": 0,
        "audit_logs": 0,
    }

    department = db.scalar(select(models.Department).where(models.Department.name == DEPT_NAME))
    if department is None:
        department = models.Department(name=DEPT_NAME)
        db.add(department)
        db.flush()
        created["departments"] += 1

    users: dict[str, models.User] = {}
    for username, name, role, in_department in DEMO_USERS:
        user = db.scalar(select(models.User).where(models.User.username == username))
        if user is None:
            user = models.User(
                username=username,
                name=name,
                role=role,
                dept_id=department.id if in_department else None,
                password_hash=auth.hash_password(DEMO_PASSWORD),
            )
            db.add(user)
            db.flush()
            created["users"] += 1
        users[username] = user

    weeks: dict[int, models.Week] = {}
    for spec in DEMO_WEEKS:
        week = db.scalar(select(models.Week).where(models.Week.week_no == spec["week_no"]))
        if week is None:
            week = models.Week(
                week_no=spec["week_no"],
                start_date=spec["start_date"],
                end_date=spec["end_date"],
                deadline=spec["deadline"],
            )
            db.add(week)
            db.flush()
            created["weeks"] += 1
        weeks[week.week_no] = week

    for week_no, member_data in DEMO_REPORTS.items():
        week = weeks[week_no]
        submitted_at = datetime.combine(week.end_date, time(18, 0))
        for username, items in member_data.items():
            user = users[username]
            existing = db.scalar(
                select(models.MemberReport).where(
                    models.MemberReport.user_id == user.id,
                    models.MemberReport.week_id == week.id,
                )
            )
            if existing is not None:
                continue

            report = models.MemberReport(
                user_id=user.id,
                week_id=week.id,
                status=models.MemberReportStatus.SUBMITTED.value,
                version=1,
                locked=True,
                done_items=list(items["done"]),
                plan_items=list(items["plan"]),
                issue_items=list(items["issue"]),
                coord_items=list(items["coord"]),
                submitted_at=submitted_at,
            )
            db.add(report)
            db.flush()
            created["member_reports"] += 1

            snapshot = _snapshot(report)
            db.add(
                models.ReportVersion(
                    report_type="member",
                    report_id=report.id,
                    version=1,
                    snapshot_json=snapshot,
                )
            )
            db.add(
                models.AuditLog(
                    entity_type="member_report",
                    entity_id=report.id,
                    action="submit",
                    operator_id=user.id,
                    before_json=None,
                    after_json=snapshot,
                )
            )
            created["versions"] += 1
            created["audit_logs"] += 1

    db.flush()
    return {
        "created": created,
        "dept_id": department.id,
        "week_ids": {week_no: week.id for week_no, week in weeks.items()},
        "user_ids": {username: user.id for username, user in users.items()},
    }


def seed_demo_data(db: Session | None = None) -> dict[str, Any]:
    """灌入演示数据。已存在的数据不会重复插入，可安全重复执行。"""
    own_session = db is None
    session = db or SessionLocal()
    try:
        result = _seed(session)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        if own_session:
            session.close()


def reset_all_data(db: Session | None = None) -> None:
    """清空所有业务表（用于演示数据彻底重置，无需删除数据库文件）。"""
    own_session = db is None
    session = db or SessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        if own_session:
            session.close()


def main() -> None:
    # Windows 下输出到管道时默认可能是 GBK，统一为 UTF-8 避免中文乱码。
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass
    init_db()
    if "--reset" in sys.argv[1:]:
        reset_all_data()
        print("[seed] 已清空现有数据，准备重新灌入")
    result = seed_demo_data()
    created = result["created"]
    print("[seed] 演示数据已就绪（幂等，可重复执行）")
    print(f"  科室：{DEPT_NAME} (id={result['dept_id']})")
    print(
        "  本次新建："
        f"用户 {created['users']}、周次 {created['weeks']}、"
        f"成员周报 {created['member_reports']}、版本快照 {created['versions']}、审计日志 {created['audit_logs']}"
    )
    print(f"  周次：{result['week_ids']}")
    print("  演示账号：member_a / member_b / member_c / member_d / member_e / director / leader / admin")
    print(f"  统一密码：{DEMO_PASSWORD}")


if __name__ == "__main__":
    main()

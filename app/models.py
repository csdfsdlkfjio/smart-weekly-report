"""ORM 模型：用户、周次、成员周报、科室汇总稿、审计与版本快照。"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.utils import get_now


class Role(str, Enum):
    MEMBER = "member"
    DIRECTOR = "director"
    LEADER = "leader"
    ADMIN = "admin"


class MemberReportStatus(str, Enum):
    DRAFT = "草稿"
    SUBMITTED = "已提交"
    RETURNED = "已退回"


class DeptReportStatus(str, Enum):
    AGGREGATED = "已汇总"
    FINALIZED = "已定稿"
    REPORTED = "已上报"
    RETURNED = "已退回"


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_now, nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="department")
    dept_reports: Mapped[list["DeptReport"]] = relationship(back_populates="department")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    dept_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_now, nullable=False)

    department: Mapped[Department | None] = relationship(back_populates="users")
    member_reports: Mapped[list["MemberReport"]] = relationship(back_populates="user")


class Week(Base):
    __tablename__ = "weeks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week_no: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    deadline: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_now, nullable=False)


class MemberReport(Base):
    """成员周报：四类内容以 JSON 数组存储，状态严格受状态机约束。"""

    __tablename__ = "member_reports"
    __table_args__ = (UniqueConstraint("user_id", "week_id", name="uq_member_report_user_week"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    week_id: Mapped[int] = mapped_column(ForeignKey("weeks.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(16), default=MemberReportStatus.DRAFT.value, nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # 主任催报站内信标记；成员提交后清除
    is_urged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    done_items: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    plan_items: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    issue_items: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    coord_items: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    return_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=get_now, onupdate=get_now, nullable=False)

    user: Mapped[User] = relationship(back_populates="member_reports")
    week: Mapped[Week] = relationship()


class DeptReport(Base):
    """科室汇总稿：独立于成员原文，主任的编辑只发生在这里。"""

    __tablename__ = "dept_reports"
    __table_args__ = (UniqueConstraint("dept_id", "week_id", name="uq_dept_report_dept_week"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dept_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), nullable=False, index=True)
    week_id: Mapped[int] = mapped_column(ForeignKey("weeks.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(16), default=DeptReportStatus.AGGREGATED.value, nullable=False, index=True
    )
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # [{id, category, content, source_user_ids, source_names, sort_order, edited_by}]
    items: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)

    # Agent 产出：{"checked": [...], "risks": [...], "engine_trace": [...]}
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    finalized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=get_now, onupdate=get_now, nullable=False)

    department: Mapped[Department] = relationship(back_populates="dept_reports")
    week: Mapped[Week] = relationship()


class AuditLog(Base):
    """全链路操作留痕。before/after 只记录状态与变更摘要。"""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    before_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_now, nullable=False, index=True)


class ReportVersion(Base):
    """成员周报版本快照：退回/重提后仍可追溯历史内容。"""

    __tablename__ = "report_versions"
    __table_args__ = (
        UniqueConstraint("report_type", "report_id", "version", name="uq_report_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    report_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_now, nullable=False)


class SessionToken(Base):
    """登录会话：Header Token 方式，服务重启后仍可校验。"""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

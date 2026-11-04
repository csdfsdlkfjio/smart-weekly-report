"""API 契约：请求/响应模型（Pydantic v2）。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Category = Literal["done", "plan", "issue", "coord"]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    name: str
    role: str
    dept_id: int | None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class WeekOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    week_no: int
    start_date: date
    end_date: date
    deadline: datetime


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class ReportItems(BaseModel):
    done: list[str] = Field(default_factory=list)
    plan: list[str] = Field(default_factory=list)
    issue: list[str] = Field(default_factory=list)
    coord: list[str] = Field(default_factory=list)

    @field_validator("done", "plan", "issue", "coord")
    @classmethod
    def _clean(cls, values: list[str]) -> list[str]:
        return [str(v).strip() for v in values if v is not None and str(v).strip()]


class DraftRequest(ReportItems):
    week_id: int


class SubmitRequest(BaseModel):
    week_id: int


class MemberReportOut(BaseModel):
    id: int
    user_id: int
    week_id: int
    status: str
    version: int
    locked: bool
    done: list[str]
    plan: list[str]
    issue: list[str]
    coord: list[str]
    submitted_at: datetime | None = None
    returned_at: datetime | None = None
    return_reason: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, report) -> "MemberReportOut":
        return cls(
            id=report.id,
            user_id=report.user_id,
            week_id=report.week_id,
            status=report.status,
            version=report.version,
            locked=report.locked,
            done=report.done_items or [],
            plan=report.plan_items or [],
            issue=report.issue_items or [],
            coord=report.coord_items or [],
            submitted_at=report.submitted_at,
            returned_at=report.returned_at,
            return_reason=report.return_reason,
            created_at=report.created_at,
            updated_at=report.updated_at,
        )


class VersionOut(BaseModel):
    version: int
    snapshot: dict[str, Any]
    created_at: datetime


class DeptItemIn(BaseModel):
    id: str | None = None
    category: Category
    content: str
    source_user_ids: list[int] = Field(default_factory=list)
    source_names: list[str] = Field(default_factory=list)

    @field_validator("content")
    @classmethod
    def _content_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("条目内容不能为空")
        return value


class DeptItemOut(BaseModel):
    id: str
    category: str
    content: str
    source_user_ids: list[int] = Field(default_factory=list)
    source_names: list[str] = Field(default_factory=list)
    sort_order: int = 0
    edited_by: int | None = None


class DeptItemsUpdate(BaseModel):
    items: list[DeptItemIn]


class SummaryUpdate(BaseModel):
    summary: str = Field(default="", max_length=2000)


class ReturnMemberRequest(BaseModel):
    member_report_id: int
    reason: str = Field(min_length=1, max_length=500)


class AggregateRequest(BaseModel):
    week_id: int
    engine_switch: Literal["rule", "llm"] = "rule"


class EngineTraceOut(BaseModel):
    agent: str
    engine: str
    status: str
    detail: str = ""


class CheckedItemOut(BaseModel):
    item_id: str = ""
    category: str = ""
    content: str = ""
    source_user_ids: list[int] = Field(default_factory=list)
    source_names: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class RiskOut(BaseModel):
    type: str
    level: str
    user_id: int | None = None
    username: str | None = None
    user_name: str | None = None
    detail: str


class DeptReportOut(BaseModel):
    id: int
    dept_id: int
    week_id: int
    status: str
    summary: str
    items: list[DeptItemOut]
    checked: list[CheckedItemOut] = Field(default_factory=list)
    risks: list[RiskOut] = Field(default_factory=list)
    engine_trace: list[EngineTraceOut] = Field(default_factory=list)
    finalized_at: datetime | None = None
    reported_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, report) -> "DeptReportOut":
        meta = report.meta_json or {}
        return cls(
            id=report.id,
            dept_id=report.dept_id,
            week_id=report.week_id,
            status=report.status,
            summary=report.summary or "",
            items=report.items or [],
            checked=meta.get("checked", []),
            risks=meta.get("risks", []),
            engine_trace=meta.get("engine_trace", []),
            finalized_at=report.finalized_at,
            reported_at=report.reported_at,
            created_at=report.created_at,
            updated_at=report.updated_at,
        )


class LeaderReportOut(DeptReportOut):
    dept_name: str
    week_no: int


class ReturnResultOut(BaseModel):
    dept_report: DeptReportOut
    member_report: MemberReportOut


class OverviewMemberOut(BaseModel):
    user_id: int
    username: str
    name: str
    status: str
    report_id: int | None = None
    submitted_at: datetime | None = None


class OverviewOut(BaseModel):
    week_id: int
    dept_id: int
    submitted_count: int
    missing_count: int
    missing_names: list[str]
    members: list[OverviewMemberOut]


class TimelineEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    entity_id: int
    action: str
    operator_id: int | None
    before_json: dict[str, Any] | None
    after_json: dict[str, Any] | None
    created_at: datetime


class MessageOut(BaseModel):
    message: str

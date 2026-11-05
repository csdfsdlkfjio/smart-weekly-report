"""周报业务服务：状态机、数据归属校验、汇总与审计。

状态机（严格按题目）：
  成员周报：草稿 → 已提交 → 已退回 → 已提交
  科室汇总：已汇总 → 已定稿 → 已上报；已汇总/已定稿 → 已退回；已退回 → 已汇总
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDenied,
    StateTransitionError,
    ValidationError,
)
from app.models import DeptReportStatus, MemberReportStatus, Role
from app.services import ai_service, audit_service
from app.utils import get_now

MEMBER_TRANSITIONS: dict[str, set[str]] = {
    MemberReportStatus.DRAFT.value: {MemberReportStatus.SUBMITTED.value},
    MemberReportStatus.SUBMITTED.value: {MemberReportStatus.RETURNED.value},
    MemberReportStatus.RETURNED.value: {MemberReportStatus.SUBMITTED.value},
}

DEPT_TRANSITIONS: dict[str, set[str]] = {
    DeptReportStatus.AGGREGATED.value: {
        DeptReportStatus.FINALIZED.value,
        DeptReportStatus.RETURNED.value,
    },
    DeptReportStatus.FINALIZED.value: {
        DeptReportStatus.REPORTED.value,
        DeptReportStatus.RETURNED.value,
    },
    # 题目要求“任一环节主任均可发起退回”，已上报也必须能回退
    DeptReportStatus.REPORTED.value: {DeptReportStatus.RETURNED.value},
    DeptReportStatus.RETURNED.value: {DeptReportStatus.AGGREGATED.value},
}

CATEGORY_FIELDS = {
    "done": "done_items",
    "plan": "plan_items",
    "issue": "issue_items",
    "coord": "coord_items",
}


# --------------------------------------------------------------------------- #
# 通用工具
# --------------------------------------------------------------------------- #


def _clean(values: list[str] | None) -> list[str]:
    return [str(value).strip() for value in (values or []) if value is not None and str(value).strip()]


def _dedupe(values: list[Any]) -> list[Any]:
    return list(dict.fromkeys(values))


def _get_week(db: Session, week_id: int) -> models.Week:
    week = db.get(models.Week, week_id)
    if week is None:
        raise NotFoundError("周次不存在")
    return week


def _director_dept_id(director: models.User) -> int:
    if director.role != Role.DIRECTOR.value or not director.dept_id:
        raise PermissionDenied("仅科室主任可以执行该操作")
    return director.dept_id


def _log_forbidden(
    db: Session,
    operator: models.User,
    *,
    entity_type: str,
    entity_id: int,
    detail: dict[str, Any],
) -> None:
    audit_service.record(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        action="forbidden_access",
        operator_id=operator.id,
        after=detail,
    )
    db.commit()


def _snapshot_member(report: models.MemberReport) -> dict[str, Any]:
    return {
        "status": report.status,
        "version": report.version,
        "done": list(report.done_items or []),
        "plan": list(report.plan_items or []),
        "issue": list(report.issue_items or []),
        "coord": list(report.coord_items or []),
    }


def _transition_member(
    db: Session,
    report: models.MemberReport,
    target: str,
    operator: models.User,
    action: str,
    extra: dict[str, Any] | None = None,
) -> None:
    current = report.status
    if target not in MEMBER_TRANSITIONS.get(current, set()):
        raise StateTransitionError(f"成员周报状态不能从“{current}”流转到“{target}”")
    report.status = target
    audit_service.record(
        db,
        entity_type="member_report",
        entity_id=report.id,
        action=action,
        operator_id=operator.id,
        before={"status": current},
        after={"status": target, **(extra or {})},
    )


def _transition_dept(
    db: Session,
    report: models.DeptReport,
    target: str,
    operator: models.User,
    action: str,
    extra: dict[str, Any] | None = None,
) -> None:
    current = report.status
    if target not in DEPT_TRANSITIONS.get(current, set()):
        raise StateTransitionError(f"科室周报状态不能从“{current}”流转到“{target}”")
    report.status = target
    audit_service.record(
        db,
        entity_type="dept_report",
        entity_id=report.id,
        action=action,
        operator_id=operator.id,
        before={"status": current},
        after={"status": target, **(extra or {})},
    )


def _get_dept_report_owned(
    db: Session, director: models.User, dept_report_id: int
) -> models.DeptReport:
    report = db.get(models.DeptReport, dept_report_id)
    if report is None:
        raise NotFoundError("汇总稿不存在")
    dept_id = _director_dept_id(director)
    if report.dept_id != dept_id:
        _log_forbidden(
            db,
            director,
            entity_type="dept_report",
            entity_id=report.id,
            detail={"reason": "跨科室操作", "target_dept_id": report.dept_id, "own_dept_id": dept_id},
        )
        raise PermissionDenied("无权操作其他科室的汇总稿")
    return report


# --------------------------------------------------------------------------- #
# 成员侧
# --------------------------------------------------------------------------- #


def get_member_report(
    db: Session, user: models.User, week_id: int
) -> models.MemberReport | None:
    week = _get_week(db, week_id)
    return db.scalar(
        select(models.MemberReport).where(
            models.MemberReport.user_id == user.id,
            models.MemberReport.week_id == week.id,
        )
    )


def save_draft(
    db: Session,
    user: models.User,
    week_id: int,
    items: dict[str, list[str]],
) -> models.MemberReport:
    """保存草稿。已提交的周报锁定，不允许修改；已退回的周报可继续编辑。"""
    if user.role != Role.MEMBER.value:
        raise PermissionDenied("仅科室成员可以填写周报")

    week = _get_week(db, week_id)
    report = get_member_report(db, user, week.id)

    if report is not None and report.status == MemberReportStatus.SUBMITTED.value:
        raise PermissionDenied("周报已提交并锁定，不能修改")

    if report is None:
        report = models.MemberReport(
            user_id=user.id,
            week_id=week.id,
            status=MemberReportStatus.DRAFT.value,
            done_items=[],
            plan_items=[],
            issue_items=[],
            coord_items=[],
        )
        db.add(report)
        db.flush()
        action = "create_draft"
        before = None
    else:
        action = "save_draft"
        before = _snapshot_member(report)

    for category, field in CATEGORY_FIELDS.items():
        setattr(report, field, _clean(items.get(category)))

    audit_service.record(
        db,
        entity_type="member_report",
        entity_id=report.id,
        action=action,
        operator_id=user.id,
        before=before,
        after=_snapshot_member(report),
    )
    db.commit()
    db.refresh(report)
    return report


def submit_member_report(db: Session, user: models.User, week_id: int) -> models.MemberReport:
    """提交周报：校验状态、锁定内容并生成版本快照。"""
    if user.role != Role.MEMBER.value:
        raise PermissionDenied("仅科室成员可以提交周报")

    week = _get_week(db, week_id)
    report = get_member_report(db, user, week.id)
    if report is None:
        raise NotFoundError("请先保存草稿再提交")

    if report.status not in (
        MemberReportStatus.DRAFT.value,
        MemberReportStatus.RETURNED.value,
    ):
        raise StateTransitionError(f"当前状态“{report.status}”不能提交")

    if not any(
        _clean(getattr(report, field))
        for field in ("done_items", "plan_items", "issue_items", "coord_items")
    ):
        raise ValidationError("周报内容不能为空")

    action = "resubmit" if report.status == MemberReportStatus.RETURNED.value else "submit"
    report.version += 1
    report.locked = True
    report.submitted_at = get_now()
    report.returned_at = None
    report.return_reason = None
    _transition_member(
        db,
        report,
        MemberReportStatus.SUBMITTED.value,
        user,
        action,
        {
            "version": report.version,
            # 审计记录保留提交时的完整文本，供历史时间线展开查看
            "done": list(report.done_items or []),
            "plan": list(report.plan_items or []),
            "issue": list(report.issue_items or []),
            "coord": list(report.coord_items or []),
        },
    )

    db.add(
        models.ReportVersion(
            report_type="member",
            report_id=report.id,
            version=report.version,
            snapshot_json=_snapshot_member(report),
        )
    )
    db.commit()
    db.refresh(report)
    return report


def list_member_versions(db: Session, user: models.User, week_id: int) -> list[models.ReportVersion]:
    report = get_member_report(db, user, week_id)
    if report is None:
        return []
    stmt = (
        select(models.ReportVersion)
        .where(
            models.ReportVersion.report_type == "member",
            models.ReportVersion.report_id == report.id,
        )
        .order_by(models.ReportVersion.version)
    )
    return list(db.scalars(stmt))


# --------------------------------------------------------------------------- #
# 主任侧
# --------------------------------------------------------------------------- #


def get_overview(db: Session, director: models.User, week_id: int) -> dict[str, Any]:
    """提交情况看板：已交/未交成员一目了然，未提交名单供风险提示使用。"""
    dept_id = _director_dept_id(director)
    week = _get_week(db, week_id)

    members = list(
        db.scalars(
            select(models.User)
            .where(models.User.dept_id == dept_id, models.User.role == Role.MEMBER.value)
            .order_by(models.User.username)
        )
    )
    member_ids = [member.id for member in members]
    reports: dict[int, models.MemberReport] = {}
    if member_ids:
        reports = {
            report.user_id: report
            for report in db.scalars(
                select(models.MemberReport).where(
                    models.MemberReport.week_id == week.id,
                    models.MemberReport.user_id.in_(member_ids),
                )
            )
        }

    rows: list[dict[str, Any]] = []
    submitted_count = 0
    missing_names: list[str] = []
    for member in members:
        report = reports.get(member.id)
        status = report.status if report else "未提交"
        if report is not None and report.status == MemberReportStatus.SUBMITTED.value:
            submitted_count += 1
        else:
            missing_names.append(member.name)
        rows.append(
            {
                "user_id": member.id,
                "username": member.username,
                "name": member.name,
                "status": status,
                "report_id": report.id if report else None,
                "submitted_at": report.submitted_at if report else None,
            }
        )

    return {
        "week_id": week.id,
        "dept_id": dept_id,
        "submitted_count": submitted_count,
        "missing_count": len(members) - submitted_count,
        "missing_names": missing_names,
        "members": rows,
    }


def get_member_report_for_director(
    db: Session, director: models.User, member_report_id: int
) -> models.MemberReport:
    """主任查看本科室成员周报正文（退回弹窗的只读预览）。"""
    dept_id = _director_dept_id(director)
    report = db.get(models.MemberReport, member_report_id)
    if report is None:
        raise NotFoundError("成员周报不存在")

    member = db.get(models.User, report.user_id)
    if member is None or member.dept_id != dept_id:
        _log_forbidden(
            db,
            director,
            entity_type="member_report",
            entity_id=report.id,
            detail={
                "reason": "跨科室查看成员周报",
                "target_dept_id": member.dept_id if member else None,
                "own_dept_id": dept_id,
            },
        )
        raise PermissionDenied("无权查看其他科室成员的周报")
    return report


def get_dept_report_for_week(
    db: Session, director: models.User, week_id: int
) -> models.DeptReport | None:
    dept_id = _director_dept_id(director)
    week = _get_week(db, week_id)
    return db.scalar(
        select(models.DeptReport).where(
            models.DeptReport.dept_id == dept_id,
            models.DeptReport.week_id == week.id,
        )
    )


def _report_lists(report: models.MemberReport) -> dict[str, list[str]]:
    return {
        "done": [str(value) for value in (report.done_items or [])],
        "plan": [str(value) for value in (report.plan_items or [])],
        "issue": [str(value) for value in (report.issue_items or [])],
        "coord": [str(value) for value in (report.coord_items or [])],
    }


def _build_raw_items(
    db: Session, reports: list[models.MemberReport]
) -> list[dict[str, Any]]:
    """把成员周报展开为 MergerAgent 需要的扁平条目。"""
    raw_items: list[dict[str, Any]] = []
    for report in reports:
        member = db.get(models.User, report.user_id)
        user_name = member.name if member else str(report.user_id)
        for category, field in CATEGORY_FIELDS.items():
            for content in getattr(report, field) or []:
                text = str(content).strip()
                if not text:
                    continue
                raw_items.append(
                    {
                        "user_id": report.user_id,
                        "user_name": user_name,
                        "category": category,
                        "content": text,
                    }
                )
    return raw_items


def _build_risk_context(
    db: Session,
    dept_id: int,
    week: models.Week,
    reports: list[models.MemberReport],
) -> dict[str, Any]:
    """组装 RiskAgent 所需数据：成员提交状态 + 当周/上一周内容。"""
    members = list(
        db.scalars(
            select(models.User)
            .where(models.User.dept_id == dept_id, models.User.role == Role.MEMBER.value)
            .order_by(models.User.username)
        )
    )
    submitted_ids = {report.user_id for report in reports}

    current_reports: list[dict[str, Any]] = []
    for report in reports:
        member = db.get(models.User, report.user_id)
        if member is None:
            continue
        current_reports.append(
            {
                "user_id": report.user_id,
                "username": member.username,
                "name": member.name,
                **_report_lists(report),
            }
        )

    previous_week = db.scalar(
        select(models.Week).where(models.Week.week_no == week.week_no - 1)
    )
    previous_reports: list[dict[str, Any]] = []
    if previous_week is not None:
        stmt = (
            select(models.MemberReport)
            .join(models.User, models.User.id == models.MemberReport.user_id)
            .where(
                models.User.dept_id == dept_id,
                models.MemberReport.week_id == previous_week.id,
                models.MemberReport.status == MemberReportStatus.SUBMITTED.value,
            )
        )
        for report in db.scalars(stmt):
            member = db.get(models.User, report.user_id)
            if member is None:
                continue
            previous_reports.append(
                {
                    "user_id": report.user_id,
                    "username": member.username,
                    "name": member.name,
                    **_report_lists(report),
                }
            )

    return {
        "week_no": week.week_no,
        "members": [
            {
                "user_id": member.id,
                "username": member.username,
                "name": member.name,
                "submitted": member.id in submitted_ids,
            }
            for member in members
        ],
        "current_reports": current_reports,
        "previous_reports": previous_reports,
    }


def aggregate_dept_report(
    db: Session,
    director: models.User,
    week_id: int,
    engine_switch: str = "rule",
) -> models.DeptReport:
    """一键汇总：调用 LangGraph 产出归并/校验/摘要/风险，并落库。"""
    dept_id = _director_dept_id(director)
    week = _get_week(db, week_id)
    existing = get_dept_report_for_week(db, director, week.id)

    if existing is not None:
        if existing.status == DeptReportStatus.REPORTED.value:
            raise ConflictError("已上报的周报不能重新汇总")
        if existing.status in (
            DeptReportStatus.AGGREGATED.value,
            DeptReportStatus.FINALIZED.value,
        ):
            raise ConflictError("本周汇总稿已存在，请直接编辑；如需重新汇总请先退回")

    stmt = (
        select(models.MemberReport)
        .join(models.User, models.User.id == models.MemberReport.user_id)
        .where(
            models.User.dept_id == dept_id,
            models.MemberReport.week_id == week.id,
            models.MemberReport.status == MemberReportStatus.SUBMITTED.value,
        )
        .order_by(models.MemberReport.user_id)
    )
    reports = list(db.scalars(stmt))
    if not reports:
        raise ValidationError("本科室本周暂无已提交的周报，无法汇总")

    ai_result = ai_service.run_aggregate(
        dept_id=dept_id,
        week_id=week.id,
        raw_items=_build_raw_items(db, reports),
        risk_context=_build_risk_context(db, dept_id, week, reports),
        engine_switch=engine_switch,
    )
    items = ai_result["merged"]
    summary = ai_result["summary"]
    meta = {
        "checked": ai_result["checked"],
        "risks": ai_result["risks"],
        "engine_trace": ai_result["engine_trace"],
    }

    if existing is None:
        report = models.DeptReport(
            dept_id=dept_id,
            week_id=week.id,
            status=DeptReportStatus.AGGREGATED.value,
            summary=summary,
            items=items,
            meta_json=meta,
        )
        db.add(report)
        db.flush()
        audit_service.record(
            db,
            entity_type="dept_report",
            entity_id=report.id,
            action="aggregate",
            operator_id=director.id,
            before=None,
            after={
                "status": DeptReportStatus.AGGREGATED.value,
                "engine_switch": engine_switch,
                "member_report_count": len(reports),
                "item_count": len(items),
                "summary": summary,
                "items": items,
            },
        )
    else:
        report = existing
        _transition_dept(
            db,
            report,
            DeptReportStatus.AGGREGATED.value,
            director,
            "reaggregate",
            {
                "engine_switch": engine_switch,
                "member_report_count": len(reports),
                "item_count": len(items),
                "summary": summary,
                "items": items,
            },
        )
        report.items = items
        report.summary = summary
        report.meta_json = meta
        report.finalized_at = None
        report.reported_at = None

    db.commit()
    db.refresh(report)
    return report


def update_dept_items(
    db: Session,
    director: models.User,
    dept_report_id: int,
    items: list[dict[str, Any]],
) -> models.DeptReport:
    """主任编辑汇总条目：逐条改/删/补/排序。"""
    report = _get_dept_report_owned(db, director, dept_report_id)
    if report.status in (
        DeptReportStatus.FINALIZED.value,
        DeptReportStatus.REPORTED.value,
    ):
        raise StateTransitionError("已定稿/已上报的汇总稿不能编辑")
    if report.status == DeptReportStatus.RETURNED.value:
        raise StateTransitionError("汇总稿已退回，请重新汇总后再编辑")

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        category = str(item.get("category", ""))
        if category not in CATEGORY_FIELDS:
            raise ValidationError(f"非法条目类别：{category}")
        content = str(item.get("content", "")).strip()
        if not content:
            raise ValidationError("条目内容不能为空")
        normalized.append(
            {
                "id": str(item.get("id") or uuid4().hex),
                "category": category,
                "content": content,
                "source_user_ids": _dedupe([int(v) for v in (item.get("source_user_ids") or [])]),
                "source_names": _dedupe([str(v) for v in (item.get("source_names") or [])]),
                "sort_order": index,
                "edited_by": director.id,
            }
        )

    before = {"items": report.items, "status": report.status}
    report.items = normalized
    audit_service.record(
        db,
        entity_type="dept_report",
        entity_id=report.id,
        action="update_items",
        operator_id=director.id,
        before=before,
        after={"items": normalized, "status": report.status},
    )
    db.commit()
    db.refresh(report)
    return report


def update_dept_summary(
    db: Session, director: models.User, dept_report_id: int, summary: str
) -> models.DeptReport:
    report = _get_dept_report_owned(db, director, dept_report_id)
    if report.status in (
        DeptReportStatus.FINALIZED.value,
        DeptReportStatus.REPORTED.value,
    ):
        raise StateTransitionError("已定稿/已上报的汇总稿不能编辑")
    if report.status == DeptReportStatus.RETURNED.value:
        raise StateTransitionError("汇总稿已退回，请重新汇总后再编辑")

    before = {"summary": report.summary}
    report.summary = summary.strip()
    audit_service.record(
        db,
        entity_type="dept_report",
        entity_id=report.id,
        action="update_summary",
        operator_id=director.id,
        before=before,
        after={"summary": report.summary},
    )
    db.commit()
    db.refresh(report)
    return report


def return_member_report(
    db: Session,
    director: models.User,
    dept_report_id: int,
    member_report_id: int,
    reason: str,
) -> tuple[models.DeptReport, models.MemberReport]:
    """主任退回指定成员周报：附理由、解除锁定、保留版本快照。"""
    reason = reason.strip()
    if not reason:
        raise ValidationError("退回理由不能为空")

    dept_report = _get_dept_report_owned(db, director, dept_report_id)
    if dept_report.status not in (
        DeptReportStatus.AGGREGATED.value,
        DeptReportStatus.FINALIZED.value,
        DeptReportStatus.REPORTED.value,
        DeptReportStatus.RETURNED.value,
    ):
        raise StateTransitionError(f"当前状态“{dept_report.status}”不能退回")

    member_report = db.get(models.MemberReport, member_report_id)
    if member_report is None:
        raise NotFoundError("成员周报不存在")
    if member_report.week_id != dept_report.week_id:
        raise ValidationError("成员周报与汇总稿不属于同一周次")
    member = db.get(models.User, member_report.user_id)
    if member is None or member.dept_id != dept_report.dept_id:
        raise ValidationError("成员周报不属于该科室")

    if member_report.status != MemberReportStatus.SUBMITTED.value:
        raise StateTransitionError("只能退回已提交的成员周报")

    if dept_report.status != DeptReportStatus.RETURNED.value:
        _transition_dept(
            db,
            dept_report,
            DeptReportStatus.RETURNED.value,
            director,
            "return",
            {"member_report_id": member_report.id, "reason": reason},
        )
        # 定稿/上报已失效，清空对应时间，需重新汇总、定稿、上报
        dept_report.finalized_at = None
        dept_report.reported_at = None
    else:
        audit_service.record(
            db,
            entity_type="dept_report",
            entity_id=dept_report.id,
            action="return",
            operator_id=director.id,
            before={"status": dept_report.status},
            after={
                "status": dept_report.status,
                "member_report_id": member_report.id,
                "reason": reason,
            },
        )

    member_report.locked = False
    member_report.return_reason = reason
    member_report.returned_at = get_now()
    _transition_member(
        db,
        member_report,
        MemberReportStatus.RETURNED.value,
        director,
        "return",
        {"reason": reason},
    )
    db.commit()
    db.refresh(dept_report)
    db.refresh(member_report)
    return dept_report, member_report


def finalize_dept_report(
    db: Session, director: models.User, dept_report_id: int
) -> models.DeptReport:
    report = _get_dept_report_owned(db, director, dept_report_id)
    if not report.items:
        raise ValidationError("汇总稿没有条目，不能定稿")
    report.finalized_at = get_now()
    _transition_dept(
        db,
        report,
        DeptReportStatus.FINALIZED.value,
        director,
        "finalize",
        {"item_count": len(report.items)},
    )
    db.commit()
    db.refresh(report)
    return report


def report_dept_report(
    db: Session, director: models.User, dept_report_id: int
) -> models.DeptReport:
    report = _get_dept_report_owned(db, director, dept_report_id)
    report.reported_at = get_now()
    _transition_dept(
        db,
        report,
        DeptReportStatus.REPORTED.value,
        director,
        "report",
        {"item_count": len(report.items)},
    )
    db.commit()
    db.refresh(report)
    return report


# --------------------------------------------------------------------------- #
# 院领导 / 审计
# --------------------------------------------------------------------------- #


def track_item(
    db: Session,
    director: models.User,
    keyword: str,
    dept_id: int | None = None,
) -> dict[str, Any]:
    """跨周追踪某个关键词：从首次出现周开始，逐周返回进展。"""
    own_dept_id = _director_dept_id(director)
    if dept_id is not None and dept_id != own_dept_id:
        _log_forbidden(
            db,
            director,
            entity_type="department",
            entity_id=dept_id,
            detail={
                "reason": "跨科室追踪事项",
                "requested_dept_id": dept_id,
                "own_dept_id": own_dept_id,
            },
        )
        raise PermissionDenied("无权追踪其他科室的事项")

    keyword = keyword.strip()
    if not keyword:
        raise ValidationError("追踪关键词不能为空")

    weeks = list(db.scalars(select(models.Week).order_by(models.Week.week_no)))
    if not weeks:
        return {
            "keyword": keyword,
            "dept_id": own_dept_id,
            "found": False,
            "timeline": [],
        }

    stmt = (
        select(models.MemberReport, models.User)
        .join(models.User, models.User.id == models.MemberReport.user_id)
        .where(models.User.dept_id == own_dept_id)
    )
    matches_by_week: dict[int, list[dict[str, Any]]] = {}
    needle = keyword.casefold()

    for report, member in db.execute(stmt):
        for category, field in CATEGORY_FIELDS.items():
            for content in getattr(report, field) or []:
                text = str(content).strip()
                if needle in text.casefold():
                    matches_by_week.setdefault(report.week_id, []).append(
                        {
                            "user_id": report.user_id,
                            "user_name": member.name,
                            "category": category,
                            "content": text,
                            "report_status": report.status,
                        }
                    )

    first_match_index = next(
        (index for index, week in enumerate(weeks) if week.id in matches_by_week),
        None,
    )
    if first_match_index is None:
        return {
            "keyword": keyword,
            "dept_id": own_dept_id,
            "found": False,
            "timeline": [],
        }

    timeline: list[dict[str, Any]] = []
    for week in weeks[first_match_index:]:
        items = matches_by_week.get(week.id, [])
        timeline.append(
            {
                "week_id": week.id,
                "week_no": week.week_no,
                "start_date": week.start_date,
                "end_date": week.end_date,
                "status": "matched" if items else "not_progressed",
                "items": items,
            }
        )

    return {
        "keyword": keyword,
        "dept_id": own_dept_id,
        "found": True,
        "timeline": timeline,
    }


def list_reported_reports(
    db: Session,
    *,
    week_id: int | None = None,
    dept_id: int | None = None,
) -> list[models.DeptReport]:
    stmt = (
        select(models.DeptReport)
        .where(models.DeptReport.status == DeptReportStatus.REPORTED.value)
        .order_by(models.DeptReport.week_id.desc(), models.DeptReport.dept_id)
    )
    if week_id is not None:
        stmt = stmt.where(models.DeptReport.week_id == week_id)
    if dept_id is not None:
        stmt = stmt.where(models.DeptReport.dept_id == dept_id)
    return list(db.scalars(stmt))


def get_reported_report(db: Session, dept_report_id: int) -> models.DeptReport:
    report = db.get(models.DeptReport, dept_report_id)
    if report is None or report.status != DeptReportStatus.REPORTED.value:
        # 未上报的稿件对院领导不可见，统一返回 404，避免泄露存在性。
        raise NotFoundError("周报不存在或尚未上报")
    return report


def get_timeline(
    db: Session, user: models.User, entity_type: str, entity_id: int
) -> list[models.AuditLog]:
    """操作时间线：主任只能看本科室，院领导只能看已上报汇总稿，管理员可查全部。"""
    if entity_type == "member_report":
        report = db.get(models.MemberReport, entity_id)
        if report is None:
            raise NotFoundError("成员周报不存在")
        member = db.get(models.User, report.user_id)
        if user.role == Role.DIRECTOR.value:
            if not user.dept_id or member is None or member.dept_id != user.dept_id:
                raise PermissionDenied("无权查看其他科室的操作记录")
        elif user.role == Role.MEMBER.value:
            if report.user_id != user.id:
                raise PermissionDenied("只能查看本人周报的操作记录")
        elif user.role != Role.ADMIN.value:
            raise PermissionDenied("无权查看该操作记录")
    elif entity_type == "dept_report":
        report = db.get(models.DeptReport, entity_id)
        if report is None:
            raise NotFoundError("汇总稿不存在")
        if user.role == Role.DIRECTOR.value:
            if not user.dept_id or report.dept_id != user.dept_id:
                raise PermissionDenied("无权查看其他科室的操作记录")
        elif user.role == Role.LEADER.value:
            if report.status != DeptReportStatus.REPORTED.value:
                raise NotFoundError("周报不存在或尚未上报")
        elif user.role != Role.ADMIN.value:
            raise PermissionDenied("无权查看该操作记录")
    else:
        raise ValidationError(f"不支持的实体类型：{entity_type}")

    return audit_service.list_timeline(db, entity_type, entity_id)


def list_weeks(db: Session) -> list[models.Week]:
    return list(db.scalars(select(models.Week).order_by(models.Week.week_no.desc())))


def list_departments(db: Session) -> list[models.Department]:
    return list(db.scalars(select(models.Department).order_by(models.Department.name)))

"""科室主任：提交看板、汇总、编辑、退回、定稿、上报。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import auth, models, schemas
from app.db import get_db
from app.models import Role
from app.services import report_service

router = APIRouter(prefix="/api/director", tags=["director"])

DirectorUser = Annotated[models.User, Depends(auth.require_role(Role.DIRECTOR.value))]


@router.get("/overview", response_model=schemas.OverviewOut)
def overview(
    current_user: DirectorUser,
    week_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
) -> schemas.OverviewOut:
    return schemas.OverviewOut(**report_service.get_overview(db, current_user, week_id))


@router.post("/aggregate", response_model=schemas.DeptReportOut)
def aggregate(
    payload: schemas.AggregateRequest,
    current_user: DirectorUser,
    db: Session = Depends(get_db),
) -> schemas.DeptReportOut:
    report = report_service.aggregate_dept_report(
        db, current_user, payload.week_id, payload.engine_switch
    )
    return schemas.DeptReportOut.from_model(report)


@router.get("/member-report/{member_report_id}", response_model=schemas.MemberReportOut)
def get_member_report(
    member_report_id: int,
    current_user: DirectorUser,
    db: Session = Depends(get_db),
) -> schemas.MemberReportOut:
    report = report_service.get_member_report_for_director(db, current_user, member_report_id)
    return schemas.MemberReportOut.from_model(report)


@router.get("/dept-report", response_model=schemas.DeptReportOut | None)
def get_dept_report(
    current_user: DirectorUser,
    week_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
) -> schemas.DeptReportOut | None:
    report = report_service.get_dept_report_for_week(db, current_user, week_id)
    return schemas.DeptReportOut.from_model(report) if report else None


@router.put("/dept-report/{dept_report_id}/items", response_model=schemas.DeptReportOut)
def update_items(
    dept_report_id: int,
    payload: schemas.DeptItemsUpdate,
    current_user: DirectorUser,
    db: Session = Depends(get_db),
) -> schemas.DeptReportOut:
    report = report_service.update_dept_items(
        db,
        current_user,
        dept_report_id,
        [item.model_dump() for item in payload.items],
    )
    return schemas.DeptReportOut.from_model(report)


@router.put("/dept-report/{dept_report_id}/summary", response_model=schemas.DeptReportOut)
def update_summary(
    dept_report_id: int,
    payload: schemas.SummaryUpdate,
    current_user: DirectorUser,
    db: Session = Depends(get_db),
) -> schemas.DeptReportOut:
    report = report_service.update_dept_summary(db, current_user, dept_report_id, payload.summary)
    return schemas.DeptReportOut.from_model(report)


@router.post("/dept-report/{dept_report_id}/return", response_model=schemas.ReturnResultOut)
def return_member(
    dept_report_id: int,
    payload: schemas.ReturnMemberRequest,
    current_user: DirectorUser,
    db: Session = Depends(get_db),
) -> schemas.ReturnResultOut:
    dept_report, member_report = report_service.return_member_report(
        db,
        current_user,
        dept_report_id,
        payload.member_report_id,
        payload.reason,
    )
    return schemas.ReturnResultOut(
        dept_report=schemas.DeptReportOut.from_model(dept_report),
        member_report=schemas.MemberReportOut.from_model(member_report),
    )


@router.post("/dept-report/{dept_report_id}/finalize", response_model=schemas.DeptReportOut)
def finalize(
    dept_report_id: int,
    current_user: DirectorUser,
    db: Session = Depends(get_db),
) -> schemas.DeptReportOut:
    report = report_service.finalize_dept_report(db, current_user, dept_report_id)
    return schemas.DeptReportOut.from_model(report)


@router.post("/dept-report/{dept_report_id}/report", response_model=schemas.DeptReportOut)
def report_up(
    dept_report_id: int,
    current_user: DirectorUser,
    db: Session = Depends(get_db),
) -> schemas.DeptReportOut:
    report = report_service.report_dept_report(db, current_user, dept_report_id)
    return schemas.DeptReportOut.from_model(report)

"""院领导：按周次/科室查阅已上报周报（只读）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import auth, models, schemas
from app.db import get_db
from app.models import Role
from app.services import report_service

router = APIRouter(prefix="/api/leader", tags=["leader"])

LeaderUser = Annotated[models.User, Depends(auth.require_role(Role.LEADER.value))]


def _to_leader_out(report: models.DeptReport) -> schemas.LeaderReportOut:
    base = schemas.DeptReportOut.from_model(report)
    return schemas.LeaderReportOut(
        **base.model_dump(),
        dept_name=report.department.name if report.department else "",
        week_no=report.week.week_no if report.week else 0,
    )


@router.get("/reports", response_model=list[schemas.LeaderReportOut])
def list_reports(
    _current_user: LeaderUser,
    week_id: int | None = Query(default=None, gt=0),
    dept_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
) -> list[schemas.LeaderReportOut]:
    reports = report_service.list_reported_reports(db, week_id=week_id, dept_id=dept_id)
    return [_to_leader_out(report) for report in reports]


@router.get("/reports/{dept_report_id}", response_model=schemas.LeaderReportOut)
def get_report(
    dept_report_id: int,
    _current_user: LeaderUser,
    db: Session = Depends(get_db),
) -> schemas.LeaderReportOut:
    report = report_service.get_reported_report(db, dept_report_id)
    return _to_leader_out(report)

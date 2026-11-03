"""科室成员：查看/保存草稿/提交本人周报。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import auth, models, schemas
from app.db import get_db
from app.models import Role
from app.services import report_service

router = APIRouter(prefix="/api/member", tags=["member"])

MemberUser = Annotated[models.User, Depends(auth.require_role(Role.MEMBER.value))]


@router.get("/report", response_model=schemas.MemberReportOut | None)
def get_report(
    current_user: MemberUser,
    week_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
) -> schemas.MemberReportOut | None:
    report = report_service.get_member_report(db, current_user, week_id)
    return schemas.MemberReportOut.from_model(report) if report else None


@router.post("/report/draft", response_model=schemas.MemberReportOut)
def save_draft(
    payload: schemas.DraftRequest,
    current_user: MemberUser,
    db: Session = Depends(get_db),
) -> schemas.MemberReportOut:
    report = report_service.save_draft(
        db,
        current_user,
        payload.week_id,
        {
            "done": payload.done,
            "plan": payload.plan,
            "issue": payload.issue,
            "coord": payload.coord,
        },
    )
    return schemas.MemberReportOut.from_model(report)


@router.post("/report/submit", response_model=schemas.MemberReportOut)
def submit_report(
    payload: schemas.SubmitRequest,
    current_user: MemberUser,
    db: Session = Depends(get_db),
) -> schemas.MemberReportOut:
    report = report_service.submit_member_report(db, current_user, payload.week_id)
    return schemas.MemberReportOut.from_model(report)


@router.get("/report/versions", response_model=list[schemas.VersionOut])
def list_versions(
    current_user: MemberUser,
    week_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
) -> list[schemas.VersionOut]:
    versions = report_service.list_member_versions(db, current_user, week_id)
    return [
        schemas.VersionOut(
            version=item.version,
            snapshot=item.snapshot_json,
            created_at=item.created_at,
        )
        for item in versions
    ]

"""操作时间线：主任看本科室，院领导看已上报汇总稿，管理员可查全部。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import auth, models, schemas
from app.db import get_db
from app.models import Role
from app.services import report_service

router = APIRouter(prefix="/api/audit", tags=["audit"])

AuditUser = Annotated[
    models.User,
    Depends(auth.require_role(Role.DIRECTOR.value, Role.LEADER.value, Role.ADMIN.value)),
]


@router.get("/{entity_type}/{entity_id}", response_model=list[schemas.TimelineEventOut])
def timeline(
    entity_type: str,
    entity_id: int,
    current_user: AuditUser,
    db: Session = Depends(get_db),
) -> list[schemas.TimelineEventOut]:
    logs = report_service.get_timeline(db, current_user, entity_type, entity_id)
    return [schemas.TimelineEventOut.model_validate(log) for log in logs]

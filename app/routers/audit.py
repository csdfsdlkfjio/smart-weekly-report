"""操作时间线：主任看本科室，院领导看已上报汇总稿，管理员可查全部。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth, models, schemas
from app.db import get_db
from app.models import Role
from app.services import report_service

router = APIRouter(prefix="/api/audit", tags=["audit"])

AuditUser = Annotated[
    models.User,
    Depends(
        auth.require_role(
            Role.MEMBER.value,
            Role.DIRECTOR.value,
            Role.LEADER.value,
            Role.ADMIN.value,
        )
    ),
]


@router.get("/{entity_type}/{entity_id}", response_model=list[schemas.TimelineEventOut])
def timeline(
    entity_type: str,
    entity_id: int,
    current_user: AuditUser,
    db: Session = Depends(get_db),
) -> list[schemas.TimelineEventOut]:
    logs = report_service.get_timeline(db, current_user, entity_type, entity_id)

    operator_ids = {log.operator_id for log in logs if log.operator_id is not None}
    names: dict[int, str] = {}
    if operator_ids:
        names = {
            user.id: user.name
            for user in db.scalars(
                select(models.User).where(models.User.id.in_(operator_ids))
            )
        }

    events: list[schemas.TimelineEventOut] = []
    for log in logs:
        event = schemas.TimelineEventOut.model_validate(log)
        event.operator_name = names.get(log.operator_id) if log.operator_id else None
        events.append(event)
    return events

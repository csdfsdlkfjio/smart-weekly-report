"""审计服务：任何业务写操作后的统一留痕入口。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


def record(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
    action: str,
    operator_id: int | None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> models.AuditLog:
    log = models.AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        operator_id=operator_id,
        before_json=before,
        after_json=after,
    )
    db.add(log)
    return log


def list_timeline(db: Session, entity_type: str, entity_id: int) -> list[models.AuditLog]:
    stmt = (
        select(models.AuditLog)
        .where(
            models.AuditLog.entity_type == entity_type,
            models.AuditLog.entity_id == entity_id,
        )
        # 时间线按时间倒序：最新操作在前
        .order_by(models.AuditLog.created_at.desc(), models.AuditLog.id.desc())
    )
    return list(db.scalars(stmt))

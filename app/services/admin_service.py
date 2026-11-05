"""系统管理员只读查询。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


def list_users(db: Session) -> list[dict[str, Any]]:
    users = list(
        db.scalars(select(models.User).order_by(models.User.role, models.User.username))
    )
    return [
        {
            "id": user.id,
            "username": user.username,
            "name": user.name,
            "role": user.role,
            "dept_id": user.dept_id,
            "dept_name": user.department.name if user.department else None,
        }
        for user in users
    ]

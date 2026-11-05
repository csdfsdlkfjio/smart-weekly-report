"""系统管理员：只读查看用户列表。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import auth, models, schemas
from app.db import get_db
from app.models import Role
from app.services import admin_service

router = APIRouter(prefix="/api/admin", tags=["admin"])

AdminUser = Annotated[models.User, Depends(auth.require_role(Role.ADMIN.value))]


@router.get("/users", response_model=list[schemas.AdminUserOut])
def list_users(
    _current_user: AdminUser,
    db: Session = Depends(get_db),
) -> list[schemas.AdminUserOut]:
    return [
        schemas.AdminUserOut(**row)
        for row in admin_service.list_users(db)
    ]

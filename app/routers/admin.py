"""系统管理员：用户、科室与周次的极简维护。"""

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


@router.post("/users", response_model=schemas.AdminUserOut, status_code=201)
def create_user(
    payload: schemas.AdminUserCreate,
    current_user: AdminUser,
    db: Session = Depends(get_db),
) -> schemas.AdminUserOut:
    return schemas.AdminUserOut(**admin_service.create_user(db, current_user, payload))


@router.put("/users/{user_id}", response_model=schemas.AdminUserOut)
def update_user(
    user_id: int,
    payload: schemas.AdminUserUpdate,
    current_user: AdminUser,
    db: Session = Depends(get_db),
) -> schemas.AdminUserOut:
    return schemas.AdminUserOut(
        **admin_service.update_user(db, current_user, user_id, payload)
    )


@router.post("/departments", response_model=schemas.DepartmentOut, status_code=201)
def create_department(
    payload: schemas.AdminDepartmentCreate,
    current_user: AdminUser,
    db: Session = Depends(get_db),
) -> schemas.DepartmentOut:
    department = admin_service.create_department(db, current_user, payload)
    return schemas.DepartmentOut.model_validate(department)


@router.post("/weeks", response_model=schemas.WeekOut, status_code=201)
def create_week(
    payload: schemas.AdminWeekCreate,
    current_user: AdminUser,
    db: Session = Depends(get_db),
) -> schemas.WeekOut:
    week = admin_service.create_week(db, current_user, payload)
    return schemas.WeekOut.model_validate(week)


@router.put("/weeks/{week_id}/deadline", response_model=schemas.WeekOut)
def update_week_deadline(
    week_id: int,
    payload: schemas.AdminWeekDeadlineUpdate,
    current_user: AdminUser,
    db: Session = Depends(get_db),
) -> schemas.WeekOut:
    week = admin_service.update_week_deadline(db, current_user, week_id, payload)
    return schemas.WeekOut.model_validate(week)

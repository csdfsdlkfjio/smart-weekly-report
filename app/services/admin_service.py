"""系统管理员：用户、科室与周次的极简维护。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import auth, models, schemas
from app.exceptions import ConflictError, NotFoundError, ValidationError
from app.services import audit_service


def user_to_dict(user: models.User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "name": user.name,
        "role": user.role,
        "dept_id": user.dept_id,
        "dept_name": user.department.name if user.department else None,
    }


def list_users(db: Session) -> list[dict[str, Any]]:
    users = list(
        db.scalars(select(models.User).order_by(models.User.role, models.User.username))
    )
    return [user_to_dict(user) for user in users]


def _resolve_dept_id(db: Session, role: str, dept_id: int | None) -> int | None:
    if role in (models.Role.MEMBER.value, models.Role.DIRECTOR.value):
        if dept_id is None:
            raise ValidationError("科室成员/主任必须选择所属科室")
        department = db.get(models.Department, dept_id)
        if department is None:
            raise ValidationError("所属科室不存在")
        return department.id
    # 院领导 / 管理员不归属具体科室
    return None


def create_user(
    db: Session, admin: models.User, payload: schemas.AdminUserCreate
) -> dict[str, Any]:
    if db.scalar(select(models.User).where(models.User.username == payload.username)):
        raise ConflictError("用户名已存在")

    dept_id = _resolve_dept_id(db, payload.role, payload.dept_id)
    user = models.User(
        username=payload.username,
        name=payload.name,
        role=payload.role,
        dept_id=dept_id,
        password_hash=auth.hash_password(payload.password),
        is_active=True,
    )
    db.add(user)
    try:
        db.flush()
        audit_service.record(
            db,
            entity_type="admin_user",
            entity_id=user.id,
            action="create_user",
            operator_id=admin.id,
            after={
                "username": user.username,
                "name": user.name,
                "role": user.role,
                "dept_id": user.dept_id,
            },
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("用户名已存在")
    db.refresh(user)
    return user_to_dict(user)


def update_user(
    db: Session, admin: models.User, user_id: int, payload: schemas.AdminUserUpdate
) -> dict[str, Any]:
    user = db.get(models.User, user_id)
    if user is None:
        raise NotFoundError("用户不存在")

    before = {"name": user.name, "role": user.role, "dept_id": user.dept_id}
    dept_id = _resolve_dept_id(db, payload.role, payload.dept_id)
    user.name = payload.name
    user.role = payload.role
    user.dept_id = dept_id
    password_reset = bool(payload.password)
    if password_reset:
        user.password_hash = auth.hash_password(payload.password)

    audit_service.record(
        db,
        entity_type="admin_user",
        entity_id=user.id,
        action="update_user",
        operator_id=admin.id,
        before=before,
        after={
            "name": user.name,
            "role": user.role,
            "dept_id": user.dept_id,
            "password_reset": password_reset,
        },
    )
    db.commit()
    db.refresh(user)
    return user_to_dict(user)


def create_department(
    db: Session, admin: models.User, payload: schemas.AdminDepartmentCreate
) -> models.Department:
    if db.scalar(select(models.Department).where(models.Department.name == payload.name)):
        raise ConflictError("科室名称已存在")

    department = models.Department(name=payload.name)
    db.add(department)
    try:
        db.flush()
        audit_service.record(
            db,
            entity_type="department",
            entity_id=department.id,
            action="create_department",
            operator_id=admin.id,
            after={"name": department.name},
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("科室名称已存在")
    db.refresh(department)
    return department


def create_week(
    db: Session, admin: models.User, payload: schemas.AdminWeekCreate
) -> models.Week:
    if db.scalar(select(models.Week).where(models.Week.week_no == payload.week_no)):
        raise ConflictError(f"第 {payload.week_no} 周已存在")

    week = models.Week(
        week_no=payload.week_no,
        start_date=payload.start_date,
        end_date=payload.end_date,
        deadline=payload.deadline,
    )
    db.add(week)
    try:
        db.flush()
        audit_service.record(
            db,
            entity_type="week",
            entity_id=week.id,
            action="create_week",
            operator_id=admin.id,
            after={
                "week_no": week.week_no,
                "start_date": str(week.start_date),
                "end_date": str(week.end_date),
                "deadline": str(week.deadline),
            },
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError(f"第 {payload.week_no} 周已存在")
    db.refresh(week)
    return week


def update_week_deadline(
    db: Session,
    admin: models.User,
    week_id: int,
    payload: schemas.AdminWeekDeadlineUpdate,
) -> models.Week:
    week = db.get(models.Week, week_id)
    if week is None:
        raise NotFoundError("周次不存在")
    if payload.deadline.date() < week.end_date:
        raise ValidationError("截止时间不能早于周次结束日期")

    before = {"deadline": str(week.deadline)}
    week.deadline = payload.deadline
    audit_service.record(
        db,
        entity_type="week",
        entity_id=week.id,
        action="update_week_deadline",
        operator_id=admin.id,
        before=before,
        after={"deadline": str(week.deadline)},
    )
    db.commit()
    db.refresh(week)
    return week

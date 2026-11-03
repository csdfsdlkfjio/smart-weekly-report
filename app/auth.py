"""认证与鉴权：Header Token 会话 + 角色依赖。

前端登录后拿到 token，后续请求携带 `Authorization: Bearer <token>`。
角色校验通过 `require_role(...)` 依赖工厂实现，越权访问会写审计日志。
"""

from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Annotated

import bcrypt
from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, models
from app.db import get_db
from app.exceptions import AuthenticationError, PermissionDenied
from app.services import audit_service


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_session(db: Session, user: models.User) -> str:
    """创建登录会话并返回 token。"""
    raw_token = secrets.token_urlsafe(32)
    db.add(
        models.SessionToken(
            token=raw_token,
            user_id=user.id,
            expires_at=models.utcnow() + timedelta(hours=config.SESSION_TTL_HOURS),
        )
    )
    db.commit()
    return raw_token


def revoke_user_sessions(db: Session, user: models.User) -> None:
    for row in db.scalars(select(models.SessionToken).where(models.SessionToken.user_id == user.id)):
        db.delete(row)
    db.commit()


def get_current_user(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    db: Session = Depends(get_db),
) -> models.User:
    """从 Authorization: Bearer <token> 解析当前用户。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthenticationError("未登录或登录已失效")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise AuthenticationError("未登录或登录已失效")

    session = db.scalar(select(models.SessionToken).where(models.SessionToken.token == token))
    if session is None:
        raise AuthenticationError("未登录或登录已失效")
    if session.expires_at <= models.utcnow():
        db.delete(session)
        db.commit()
        raise AuthenticationError("登录已过期，请重新登录")

    user = db.get(models.User, session.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("账号不存在或已停用")
    return user


def require_role(*allowed_roles: str):
    """依赖工厂：校验当前用户角色，越权时留痕并返回 403。"""

    def dependency(
        current_user: models.User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> models.User:
        if current_user.role not in allowed_roles:
            audit_service.record(
                db,
                entity_type="auth",
                entity_id=current_user.id,
                action="forbidden_access",
                operator_id=current_user.id,
                after={
                    "required_roles": list(allowed_roles),
                    "actual_role": current_user.role,
                },
            )
            db.commit()
            raise PermissionDenied("当前角色无权访问该功能")
        return current_user

    return dependency

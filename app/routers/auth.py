"""登录 / 登出 / 当前用户。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth, models, schemas
from app.db import get_db
from app.exceptions import AuthenticationError

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=schemas.TokenOut)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)) -> schemas.TokenOut:
    user = db.scalar(select(models.User).where(models.User.username == payload.username))
    if (
        user is None
        or not user.is_active
        or not auth.verify_password(payload.password, user.password_hash)
    ):
        raise AuthenticationError("用户名或密码错误")

    token = auth.create_session(db, user)
    return schemas.TokenOut(access_token=token, user=schemas.UserOut.model_validate(user))


@router.post("/logout", response_model=schemas.MessageOut)
def logout(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
) -> schemas.MessageOut:
    auth.revoke_user_sessions(db, current_user)
    return schemas.MessageOut(message="已退出登录")


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(auth.get_current_user)) -> schemas.UserOut:
    return schemas.UserOut.model_validate(current_user)

"""通用元数据：周次列表。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import auth, models, schemas
from app.db import get_db
from app.services import report_service

router = APIRouter(prefix="/api", tags=["meta"])

CurrentUser = Annotated[models.User, Depends(auth.get_current_user)]


@router.get("/weeks", response_model=list[schemas.WeekOut])
def list_weeks(
    _current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> list[schemas.WeekOut]:
    return [schemas.WeekOut.model_validate(week) for week in report_service.list_weeks(db)]

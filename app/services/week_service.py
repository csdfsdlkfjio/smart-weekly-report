"""周次自动生成。

规则：
- 空库：生成包含今天的当前周（周一至周日）
- 最新周 end_date 早于今天：按周一至周日顺延，直到覆盖今天
- 截止时间沿用演示约定：周日后的周二 23:59
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.db import SessionLocal


def _monday_of(day: date) -> date:
    """返回 day 所在周的周一。"""
    return day - timedelta(days=day.weekday())


def _monday_on_or_after(day: date) -> date:
    """返回 day 当天或之后最近的周一。"""
    return day + timedelta(days=(7 - day.weekday()) % 7)


def _week_spec(week_no: int, start: date) -> dict[str, Any]:
    start = _monday_on_or_after(start)
    end = start + timedelta(days=6)
    # 与演示数据保持一致：周日晚 23:59 截止后，周二 23:59 前提交
    deadline = datetime.combine(end + timedelta(days=2), time(23, 59))
    return {
        "week_no": week_no,
        "start_date": start,
        "end_date": end,
        "deadline": deadline,
    }


def ensure_current_week(
    db: Session | None = None,
    today: date | None = None,
) -> list[models.Week]:
    """确保数据库中存在覆盖今天的周次，返回本次新建的周次列表。"""
    own_session = db is None
    session = db or SessionLocal()
    created: list[models.Week] = []
    try:
        target_day = today or date.today()
        latest = session.scalar(
            select(models.Week).order_by(models.Week.week_no.desc()).limit(1)
        )

        if latest is None:
            spec = _week_spec(1, _monday_of(target_day))
            latest = models.Week(**spec)
            session.add(latest)
            session.flush()
            created.append(latest)

        while latest.end_date < target_day:
            # 下一个周次必须从最新周结束后的下一个周一开始，避免日期重叠
            next_start = latest.end_date + timedelta(days=1)
            spec = _week_spec(latest.week_no + 1, next_start)
            latest = models.Week(**spec)
            session.add(latest)
            session.flush()
            created.append(latest)

        session.commit()
        return created
    except Exception:
        session.rollback()
        raise
    finally:
        if own_session:
            session.close()

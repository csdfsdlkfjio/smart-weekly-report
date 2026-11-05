"""周次兜底补偿。

规则：
- 若已存在 start_date <= 今天 <= end_date 的周次，直接返回，不做任何修改；
- 若不存在，才按当前自然周（周一至周日）生成一个新的周次；
- 只插入，不更新、不删除管理员手动维护的周次。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.db import SessionLocal
from app.utils import get_now


def _week_spec(week_no: int, today: date) -> dict[str, Any]:
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)
    # 与演示数据保持一致：周日晚结束后，周二 23:59 截止
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
    """确保存在覆盖今天的周次；仅在缺失时创建一个，返回新建周次列表。"""
    own_session = db is None
    session = db or SessionLocal()
    created: list[models.Week] = []
    try:
        target_day = today or get_now().date()

        covering = session.scalar(
            select(models.Week).where(
                models.Week.start_date <= target_day,
                models.Week.end_date >= target_day,
            )
        )
        if covering is not None:
            # 已有覆盖今天的周次：绝不干扰管理员手动配置
            return []

        latest = session.scalar(
            select(models.Week).order_by(models.Week.week_no.desc()).limit(1)
        )
        next_week_no = (latest.week_no + 1) if latest is not None else 1
        week = models.Week(**_week_spec(next_week_no, target_day))
        session.add(week)
        session.commit()
        session.refresh(week)
        created.append(week)
        return created
    except Exception:
        session.rollback()
        raise
    finally:
        if own_session:
            session.close()

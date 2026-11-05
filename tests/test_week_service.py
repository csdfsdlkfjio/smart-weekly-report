"""周次兜底补偿测试。"""

from datetime import date, datetime

from sqlalchemy import select

from app import models
from app.services.week_service import ensure_current_week


def test_empty_db_creates_current_monday_to_sunday(session_factory):
    db = session_factory()
    try:
        created = ensure_current_week(db, today=date(2026, 11, 5))

        assert len(created) == 1
        week = db.scalar(select(models.Week))
        assert week.week_no == 1
        assert week.start_date == date(2026, 11, 2)
        assert week.end_date == date(2026, 11, 8)
        assert week.start_date.weekday() == 0
        assert week.end_date.weekday() == 6
        assert week.deadline == datetime(2026, 11, 10, 23, 59)
    finally:
        db.close()


def test_covering_week_is_never_modified(session_factory):
    db = session_factory()
    try:
        covering = models.Week(
            week_no=9,
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 7),
            deadline=datetime(2026, 11, 9, 18, 0),
        )
        other = models.Week(
            week_no=1,
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 7),
            deadline=datetime(2026, 10, 9, 23, 59),
        )
        db.add_all([covering, other])
        db.commit()

        created = ensure_current_week(db, today=date(2026, 11, 5))

        assert created == []
        assert db.scalar(select(models.Week).where(models.Week.week_no == 9)).deadline == datetime(
            2026, 11, 9, 18, 0
        )
        assert db.scalar(select(models.Week).where(models.Week.week_no == 2)) is None
    finally:
        db.close()


def test_creates_one_week_when_no_week_covers_today(session_factory):
    db = session_factory()
    try:
        previous = models.Week(
            week_no=2,
            start_date=date(2026, 10, 26),
            end_date=date(2026, 11, 1),
            deadline=datetime(2026, 11, 3, 23, 59),
        )
        db.add(previous)
        db.commit()

        created = ensure_current_week(db, today=date(2026, 11, 5))

        assert [week.week_no for week in created] == [3]
        week3 = db.scalar(select(models.Week).where(models.Week.week_no == 3))
        assert week3.start_date == date(2026, 11, 2)
        assert week3.end_date == date(2026, 11, 8)
        # 原有周次保持不变
        assert previous.start_date == date(2026, 10, 26)
        assert previous.end_date == date(2026, 11, 1)
    finally:
        db.close()


def test_is_idempotent_once_today_is_covered(session_factory):
    db = session_factory()
    try:
        first = ensure_current_week(db, today=date(2026, 11, 5))
        second = ensure_current_week(db, today=date(2026, 11, 5))

        assert len(first) == 1
        assert second == []
        assert len(list(db.scalars(select(models.Week)))) == 1
    finally:
        db.close()

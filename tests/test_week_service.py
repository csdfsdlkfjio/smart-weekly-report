"""自动周次生成测试。"""

from datetime import date, datetime

from sqlalchemy import select

from app import models
from app.services.week_service import ensure_current_week


def _week(week_no: int, start: date, end: date) -> models.Week:
    return models.Week(
        week_no=week_no,
        start_date=start,
        end_date=end,
        deadline=datetime.combine(end, datetime.min.time()),
    )


def test_empty_db_creates_current_monday_to_sunday(session_factory):
    db = session_factory()
    try:
        created = ensure_current_week(db, today=date(2026, 11, 4))

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


def test_creates_next_week_when_latest_has_ended(session_factory):
    db = session_factory()
    try:
        db.add(_week(2, date(2026, 10, 26), date(2026, 11, 1)))
        db.commit()

        created = ensure_current_week(db, today=date(2026, 11, 4))

        assert [week.week_no for week in created] == [3]
        week3 = db.scalar(select(models.Week).where(models.Week.week_no == 3))
        assert week3.start_date == date(2026, 11, 2)
        assert week3.end_date == date(2026, 11, 8)
        assert week3.deadline == datetime(2026, 11, 10, 23, 59)
    finally:
        db.close()


def test_catches_up_multiple_missing_weeks(session_factory):
    db = session_factory()
    try:
        db.add(_week(1, date(2026, 10, 5), date(2026, 10, 11)))
        db.commit()

        created = ensure_current_week(db, today=date(2026, 11, 4))

        assert [week.week_no for week in created] == [2, 3, 4, 5]
        weeks = list(db.scalars(select(models.Week).order_by(models.Week.week_no)))
        assert weeks[-1].start_date == date(2026, 11, 2)
        assert weeks[-1].end_date == date(2026, 11, 8)
    finally:
        db.close()


def test_is_idempotent_and_does_nothing_when_week_covers_today(session_factory):
    db = session_factory()
    try:
        db.add(_week(1, date(2026, 11, 2), date(2026, 11, 8)))
        db.commit()

        assert ensure_current_week(db, today=date(2026, 11, 4)) == []
        assert ensure_current_week(db, today=date(2026, 11, 4)) == []
        assert db.scalar(select(models.Week).where(models.Week.week_no == 2)) is None
    finally:
        db.close()

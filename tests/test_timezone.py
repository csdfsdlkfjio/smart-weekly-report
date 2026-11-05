"""北京时间统一性测试。"""

from datetime import datetime, timezone

from app.utils import BEIJING_TZ, get_now


def test_get_now_returns_beijing_wall_time():
    now = get_now()
    assert now.tzinfo is None

    expected = datetime.now(BEIJING_TZ).replace(tzinfo=None)
    assert abs((now - expected).total_seconds()) < 5

    utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs((now - utc_now).total_seconds()) > 7 * 3600


def test_submitted_at_uses_beijing_time(client, seed, login, submit_report):
    report, _ = submit_report("member_a", seed["week1_id"])

    submitted_at = datetime.fromisoformat(report["submitted_at"])
    expected = datetime.now(BEIJING_TZ).replace(tzinfo=None)
    assert abs((submitted_at - expected).total_seconds()) < 60

    utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs((submitted_at - utc_now).total_seconds()) > 7 * 3600


def test_audit_time_uses_beijing_time(client, seed, login, submit_report):
    report, headers = submit_report("member_a", seed["week1_id"])
    events = client.get(
        f"/api/audit/member_report/{report['id']}", headers=headers
    ).json()

    submitted = next(event for event in events if event["action"] == "submit")
    created_at = datetime.fromisoformat(submitted["created_at"])
    expected = datetime.now(BEIJING_TZ).replace(tzinfo=None)
    assert abs((created_at - expected).total_seconds()) < 60

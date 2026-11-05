"""跨周事项追踪接口测试。"""

from sqlalchemy import select

from app import models
from app.seed import seed_demo_data


def _track(client, headers, keyword, dept_id=None):
    params = {"keyword": keyword}
    if dept_id is not None:
        params["dept_id"] = dept_id
    return client.get("/api/director/track-item", params=params, headers=headers)


def test_track_electronic_medical_record_timeline(client, session_factory, login):
    seed_demo_data(session_factory())
    headers = login("director")

    response = _track(client, headers, "电子病历", dept_id=1)

    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert [week["week_no"] for week in body["timeline"]] == [1, 2, 3]
    assert [week["status"] for week in body["timeline"]] == [
        "matched",
        "matched",
        "not_progressed",
    ]

    week1 = body["timeline"][0]
    assert week1["items"][0]["user_name"] == "陈医生"
    assert week1["items"][0]["category"] == "plan"
    assert week1["items"][0]["content"] == "推进电子病历优化"

    week2 = body["timeline"][1]
    assert week2["items"][0]["content"] == "推进电子病历优化"
    assert body["timeline"][2]["items"] == []


def test_track_nursing_quality_matches_multiple_members(client, session_factory, login):
    seed_demo_data(session_factory())
    headers = login("director")

    response = _track(client, headers, "护理质控")

    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert [week["week_no"] for week in body["timeline"]] == [1, 2, 3]
    names = {item["user_name"] for item in body["timeline"][0]["items"]}
    assert {"张医生", "李医生"} <= names
    assert body["timeline"][0]["items"][0]["category"] == "done"
    assert body["timeline"][2]["status"] == "not_progressed"


def test_track_unknown_keyword_returns_not_found(client, session_factory, login):
    seed_demo_data(session_factory())

    response = _track(client, login("director"), "不存在的关键词")

    assert response.status_code == 200
    assert response.json()["found"] is False
    assert response.json()["timeline"] == []


def test_track_rejects_other_department(client, session_factory, login):
    seed_demo_data(session_factory())
    headers = login("director")

    response = _track(client, headers, "电子病历", dept_id=999)

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"
    with session_factory() as db:
        log = db.scalar(
            select(models.AuditLog).where(models.AuditLog.action == "forbidden_access")
        )
        assert log is not None
        assert log.entity_type == "department"


def test_track_requires_director_role(client, session_factory, login):
    seed_demo_data(session_factory())

    assert _track(client, login("member_a"), "电子病历").status_code == 403
    assert _track(client, login("leader"), "电子病历").status_code == 403


def test_track_requires_non_empty_keyword(client, session_factory, login):
    seed_demo_data(session_factory())

    response = client.get(
        "/api/director/track-item", params={"keyword": " "}, headers=login("director")
    )
    assert response.status_code == 422

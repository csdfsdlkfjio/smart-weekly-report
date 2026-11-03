"""数据归属与越权拦截测试。"""

from sqlalchemy import select

from app import models


def test_director_cannot_operate_other_department(client, seed, login, submit_report, session_factory):
    submit_report("member_a", seed["week1_id"])
    director_headers = login("director")
    aggregated = client.post(
        "/api/director/aggregate",
        json={"week_id": seed["week1_id"]},
        headers=director_headers,
    )
    assert aggregated.status_code == 200
    dept_report_id = aggregated.json()["id"]

    other_director = login("director2")
    blocked = client.put(
        f"/api/director/dept-report/{dept_report_id}/summary",
        json={"summary": "跨科室篡改"},
        headers=other_director,
    )
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "forbidden"

    with session_factory() as db:
        log = db.scalar(
            select(models.AuditLog).where(
                models.AuditLog.action == "forbidden_access",
                models.AuditLog.operator_id == seed["user_ids"]["director2"],
            )
        )
        assert log is not None
        assert log.entity_type == "dept_report"


def test_leader_cannot_return_or_finalize(client, seed, login, submit_report):
    submit_report("member_a", seed["week1_id"])
    director_headers = login("director")
    dept_report_id = client.post(
        "/api/director/aggregate",
        json={"week_id": seed["week1_id"]},
        headers=director_headers,
    ).json()["id"]

    leader_headers = login("leader")
    assert (
        client.post(
            f"/api/director/dept-report/{dept_report_id}/finalize", headers=leader_headers
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/director/dept-report/{dept_report_id}/report", headers=leader_headers
        ).status_code
        == 403
    )


def test_leader_cannot_see_unreported_report_by_id(client, seed, login, submit_report):
    submit_report("member_a", seed["week1_id"])
    director_headers = login("director")
    dept_report_id = client.post(
        "/api/director/aggregate",
        json={"week_id": seed["week1_id"]},
        headers=director_headers,
    ).json()["id"]

    response = client.get(f"/api/leader/reports/{dept_report_id}", headers=login("leader"))
    assert response.status_code == 404

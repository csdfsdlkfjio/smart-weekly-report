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


def test_director_can_read_member_report_content(client, seed, login, submit_report):
    submit_report(
        "member_a",
        seed["week1_id"],
        done=["完成护理质控检查"],
        plan=["开展护理技能培训"],
        issue=["部分病房设备老化"],
        coord=["协调设备科维修监护仪"],
    )
    director_headers = login("director")
    overview = client.get(
        "/api/director/overview",
        params={"week_id": seed["week1_id"]},
        headers=director_headers,
    ).json()
    report_id = next(
        item["report_id"] for item in overview["members"] if item["username"] == "member_a"
    )

    response = client.get(
        f"/api/director/member-report/{report_id}", headers=director_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "已提交"
    assert body["done"] == ["完成护理质控检查"]
    assert body["plan"] == ["开展护理技能培训"]
    assert body["issue"] == ["部分病房设备老化"]
    assert body["coord"] == ["协调设备科维修监护仪"]


def test_director_cannot_read_other_department_member_report(
    client, seed, login, submit_report, session_factory
):
    submit_report("member_x", seed["week1_id"], done=["骨科成员的内容"])
    member_x_headers = login("member_x")
    member_report = client.get(
        "/api/member/report",
        params={"week_id": seed["week1_id"]},
        headers=member_x_headers,
    ).json()

    response = client.get(
        f"/api/director/member-report/{member_report['id']}",
        headers=login("director"),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"
    with session_factory() as db:
        log = db.scalar(
            select(models.AuditLog).where(
                models.AuditLog.action == "forbidden_access",
                models.AuditLog.operator_id == seed["user_ids"]["director"],
            )
        )
        assert log is not None
        assert log.entity_type == "member_report"


def test_leader_cannot_use_director_member_report_endpoint(
    client, seed, login, submit_report
):
    submit_report("member_a", seed["week1_id"])
    director_headers = login("director")
    overview = client.get(
        "/api/director/overview",
        params={"week_id": seed["week1_id"]},
        headers=director_headers,
    ).json()
    report_id = next(
        item["report_id"] for item in overview["members"] if item["username"] == "member_a"
    )

    response = client.get(
        f"/api/director/member-report/{report_id}", headers=login("leader")
    )
    assert response.status_code == 403


def test_member_report_preview_returns_404_for_unknown_report(client, seed, login):
    response = client.get(
        "/api/director/member-report/999999", headers=login("director")
    )
    assert response.status_code == 404


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

"""操作时间线接口测试：成员自见、主任汇总稿、倒序与操作人姓名。"""


def test_member_can_view_own_timeline(client, seed, login, submit_report):
    submit_report("member_a", seed["week1_id"], done=["完成护理质控检查"])
    headers = login("member_a")
    report = client.get(
        "/api/member/report", params={"week_id": seed["week1_id"]}, headers=headers
    ).json()

    response = client.get(
        f"/api/audit/member_report/{report['id']}", headers=headers
    )

    assert response.status_code == 200
    events = response.json()
    assert events
    assert events[0]["action"] == "submit"
    assert events[0]["operator_name"] == "张医生"
    assert events[0]["after_json"]["done"] == ["完成护理质控检查"]
    assert events[0]["after_json"]["plan"] == ["按计划推进下周工作"]
    assert any(event["action"] == "create_draft" for event in events)


def test_member_cannot_view_other_timeline(client, seed, login, submit_report):
    submit_report("member_a", seed["week1_id"])
    member_a_headers = login("member_a")
    report = client.get(
        "/api/member/report",
        params={"week_id": seed["week1_id"]},
        headers=member_a_headers,
    ).json()

    response = client.get(
        f"/api/audit/member_report/{report['id']}", headers=login("member_b")
    )

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


def test_dept_timeline_is_descending_and_has_operator_names(client, seed, login, submit_report):
    submit_report("member_a", seed["week1_id"], done=["完成护理质控检查"])
    headers = login("director")
    aggregated = client.post(
        "/api/director/aggregate", json={"week_id": seed["week1_id"]}, headers=headers
    ).json()
    dept_report_id = aggregated["id"]
    client.put(
        f"/api/director/dept-report/{dept_report_id}/summary",
        json={"summary": "本周科室工作摘要"},
        headers=headers,
    )
    client.post(
        f"/api/director/dept-report/{dept_report_id}/finalize", headers=headers
    )

    response = client.get(
        f"/api/audit/dept_report/{dept_report_id}", headers=headers
    )

    assert response.status_code == 200
    events = response.json()
    actions = [event["action"] for event in events]
    assert actions[0] == "finalize"
    assert actions[1] == "update_summary"
    assert actions[2] == "aggregate"
    assert all(event["operator_name"] == "王主任" for event in events)
    assert [event["id"] for event in events] == sorted(
        (event["id"] for event in events), reverse=True
    )

    aggregate_event = next(event for event in events if event["action"] == "aggregate")
    assert aggregate_event["after_json"]["summary"] == "本周科室完成 1 项工作。完成事项包括：完成护理质控检查。"
    assert aggregate_event["after_json"]["items"]

    summary_event = next(event for event in events if event["action"] == "update_summary")
    assert summary_event["before_json"]["summary"] != summary_event["after_json"]["summary"]


def test_member_cannot_view_dept_timeline(client, seed, login, submit_report):
    submit_report("member_a", seed["week1_id"])
    director_headers = login("director")
    dept_report_id = client.post(
        "/api/director/aggregate",
        json={"week_id": seed["week1_id"]},
        headers=director_headers,
    ).json()["id"]

    response = client.get(
        f"/api/audit/dept_report/{dept_report_id}", headers=login("member_a")
    )

    assert response.status_code == 403


def test_audit_requires_login(client, seed):
    assert client.get("/api/audit/member_report/1").status_code == 401

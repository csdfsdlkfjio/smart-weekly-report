"""院领导按科室/周次筛选测试。"""


def _report_week(
    client,
    login,
    submit_report,
    *,
    username: str,
    director: str,
    week_id: int,
):
    submit_report(username, week_id, done=[f"{username} 的科室工作"])
    headers = login(director)
    aggregated = client.post(
        "/api/director/aggregate", json={"week_id": week_id}, headers=headers
    )
    assert aggregated.status_code == 200, aggregated.text
    dept_report_id = aggregated.json()["id"]
    assert (
        client.post(
            f"/api/director/dept-report/{dept_report_id}/finalize", headers=headers
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/director/dept-report/{dept_report_id}/report", headers=headers
        ).status_code
        == 200
    )
    return dept_report_id


def test_leader_filters_reports_by_department(client, seed, login, submit_report):
    _report_week(
        client,
        login,
        submit_report,
        username="member_a",
        director="director",
        week_id=seed["week1_id"],
    )
    _report_week(
        client,
        login,
        submit_report,
        username="member_x",
        director="director2",
        week_id=seed["week1_id"],
    )
    leader_headers = login("leader")

    all_reports = client.get("/api/leader/reports", headers=leader_headers)
    assert all_reports.status_code == 200
    assert len(all_reports.json()) == 2
    assert {item["dept_name"] for item in all_reports.json()} == {"心内科", "骨科"}

    dept1 = client.get(
        "/api/leader/reports",
        params={"dept_id": seed["dept1_id"]},
        headers=leader_headers,
    )
    assert len(dept1.json()) == 1
    assert dept1.json()[0]["dept_name"] == "心内科"

    dept2 = client.get(
        "/api/leader/reports",
        params={"dept_id": seed["dept2_id"]},
        headers=leader_headers,
    )
    assert len(dept2.json()) == 1
    assert dept2.json()[0]["dept_name"] == "骨科"

    combined = client.get(
        "/api/leader/reports",
        params={"week_id": seed["week1_id"], "dept_id": seed["dept1_id"]},
        headers=leader_headers,
    )
    assert len(combined.json()) == 1
    assert combined.json()[0]["week_no"] == 1


def test_leader_works_with_only_one_department_data(client, seed, login, submit_report):
    _report_week(
        client,
        login,
        submit_report,
        username="member_a",
        director="director",
        week_id=seed["week1_id"],
    )
    leader_headers = login("leader")

    all_reports = client.get("/api/leader/reports", headers=leader_headers).json()
    assert len(all_reports) == 1
    assert all_reports[0]["dept_name"] == "心内科"

    dept1 = client.get(
        "/api/leader/reports",
        params={"dept_id": seed["dept1_id"]},
        headers=leader_headers,
    ).json()
    assert len(dept1) == 1

    dept2 = client.get(
        "/api/leader/reports",
        params={"dept_id": seed["dept2_id"]},
        headers=leader_headers,
    ).json()
    assert dept2 == []

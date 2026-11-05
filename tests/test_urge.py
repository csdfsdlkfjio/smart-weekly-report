"""主任催报与成员站内提醒闭环测试。"""


def _urge(client, headers, week_id):
    return client.post(
        "/api/director/urge", json={"week_id": week_id}, headers=headers
    )


def test_urge_creates_notice_for_missing_members(client, seed, login):
    director_headers = login("director")

    response = _urge(client, director_headers, seed["week1_id"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["urged_count"] == 5
    assert set(body["member_names"]) == {"张医生", "李医生", "王医生", "赵医生", "陈医生"}

    member_a_headers = login("member_a")
    report = client.get(
        "/api/member/report", params={"week_id": seed["week1_id"]}, headers=member_a_headers
    ).json()
    assert report["status"] == "草稿"
    assert report["is_urged"] is True

    timeline = client.get(
        f"/api/audit/member_report/{report['id']}", headers=member_a_headers
    ).json()
    urge_event = next(event for event in timeline if event["action"] == "urge")
    assert urge_event["operator_name"] == "王主任"


def test_member_submit_clears_urge(client, seed, login):
    director_headers = login("director")
    _urge(client, director_headers, seed["week1_id"])

    member_headers = login("member_a")
    saved = client.post(
        "/api/member/report/draft",
        json={
            "week_id": seed["week1_id"],
            "done": ["完成护理质控检查"],
            "plan": ["开展培训"],
            "issue": [],
            "coord": [],
        },
        headers=member_headers,
    )
    assert saved.status_code == 200
    assert saved.json()["is_urged"] is True

    submitted = client.post(
        "/api/member/report/submit",
        json={"week_id": seed["week1_id"]},
        headers=member_headers,
    )
    assert submitted.status_code == 200
    assert submitted.json()["is_urged"] is False

    after = client.get(
        "/api/member/report", params={"week_id": seed["week1_id"]}, headers=member_headers
    ).json()
    assert after["is_urged"] is False


def test_submitted_members_are_not_urged(client, seed, login, submit_report):
    submit_report("member_a", seed["week1_id"])
    director_headers = login("director")

    response = _urge(client, director_headers, seed["week1_id"])
    assert response.json()["urged_count"] == 4
    assert "张医生" not in response.json()["member_names"]

    member_a_report = client.get(
        "/api/member/report",
        params={"week_id": seed["week1_id"]},
        headers=login("member_a"),
    ).json()
    assert member_a_report["is_urged"] is False

    member_b_report = client.get(
        "/api/member/report",
        params={"week_id": seed["week1_id"]},
        headers=login("member_b"),
    ).json()
    assert member_b_report["is_urged"] is True


def test_repeated_urge_counts_but_audits_once(client, seed, login):
    director_headers = login("director")
    first = _urge(client, director_headers, seed["week1_id"])
    second = _urge(client, director_headers, seed["week1_id"])

    assert first.json()["urged_count"] == 5
    assert second.json()["urged_count"] == 5

    member_b_headers = login("member_b")
    member_b_report = client.get(
        "/api/member/report",
        params={"week_id": seed["week1_id"]},
        headers=member_b_headers,
    ).json()
    timeline = client.get(
        f"/api/audit/member_report/{member_b_report['id']}", headers=member_b_headers
    ).json()
    urge_events = [event for event in timeline if event["action"] == "urge"]
    assert len(urge_events) == 1


def test_urge_all_submitted_returns_zero(client, seed, login, submit_report):
    for username in ("member_a", "member_b", "member_c", "member_d", "member_e"):
        submit_report(username, seed["week1_id"])

    response = _urge(client, login("director"), seed["week1_id"])

    assert response.status_code == 200
    assert response.json()["urged_count"] == 0
    assert response.json()["member_names"] == []


def test_urge_requires_director(client, seed, login):
    assert (
        _urge(client, login("member_a"), seed["week1_id"]).status_code == 403
    )
    assert _urge(client, login("leader"), seed["week1_id"]).status_code == 403

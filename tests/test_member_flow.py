"""成员周报：草稿、提交锁定、版本快照与数据隔离。"""


def _save(client, headers, week_id, *, done=None, plan=None, issue=None, coord=None):
    payload = {
        "week_id": week_id,
        "done": done or [],
        "plan": plan or [],
        "issue": issue or [],
        "coord": coord or [],
    }
    return client.post("/api/member/report/draft", json=payload, headers=headers)


def test_draft_submit_and_lock(client, seed, login):
    headers = login("member_a")

    draft = _save(client, headers, seed["week1_id"], done=["完成护理质控检查"], plan=["下周开展培训"])
    assert draft.status_code == 200
    assert draft.json()["status"] == "草稿"
    assert draft.json()["version"] == 0
    assert draft.json()["locked"] is False

    submitted = client.post(
        "/api/member/report/submit", json={"week_id": seed["week1_id"]}, headers=headers
    )
    assert submitted.status_code == 200
    body = submitted.json()
    assert body["status"] == "已提交"
    assert body["locked"] is True
    assert body["version"] == 1
    assert body["submitted_at"] is not None

    blocked = _save(client, headers, seed["week1_id"], done=["提交后再改"])
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "forbidden"

    repeated = client.post(
        "/api/member/report/submit", json={"week_id": seed["week1_id"]}, headers=headers
    )
    assert repeated.status_code == 400
    assert repeated.json()["code"] == "invalid_transition"

    versions = client.get(
        "/api/member/report/versions", params={"week_id": seed["week1_id"]}, headers=headers
    )
    assert versions.status_code == 200
    assert len(versions.json()) == 1
    assert versions.json()[0]["version"] == 1
    assert versions.json()[0]["snapshot"]["done"] == ["完成护理质控检查"]


def test_empty_report_cannot_be_submitted(client, seed, login):
    headers = login("member_a")
    assert _save(client, headers, seed["week1_id"]).status_code == 200

    response = client.post(
        "/api/member/report/submit", json={"week_id": seed["week1_id"]}, headers=headers
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_submit_without_draft_returns_404(client, seed, login):
    response = client.post(
        "/api/member/report/submit",
        json={"week_id": seed["week1_id"]},
        headers=login("member_a"),
    )

    assert response.status_code == 404


def test_member_only_sees_own_report(client, seed, login, submit_report):
    submit_report("member_a", seed["week1_id"], done=["成员A的私有内容"])

    member_b_headers = login("member_b")
    response = client.get(
        "/api/member/report", params={"week_id": seed["week1_id"]}, headers=member_b_headers
    )

    assert response.status_code == 200
    assert response.json() is None

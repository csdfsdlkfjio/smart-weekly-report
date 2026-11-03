"""鉴权与角色隔离测试。"""

from sqlalchemy import select

from app import models


def test_login_and_me(client, seed, login):
    headers = login("member_a")
    response = client.get("/api/auth/me", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "member_a"
    assert body["role"] == "member"
    assert body["dept_id"] == seed["dept1_id"]


def test_login_rejects_wrong_password(client, seed):
    response = client.post(
        "/api/auth/login",
        json={"username": "member_a", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


def test_requires_login(client, seed):
    assert client.get("/api/weeks").status_code == 401


def test_member_cannot_access_director_api_and_is_audited(client, seed, login, session_factory):
    headers = login("member_a")
    response = client.get(
        "/api/director/overview",
        params={"week_id": seed["week1_id"]},
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"

    with session_factory() as db:
        log = db.scalar(
            select(models.AuditLog).where(models.AuditLog.action == "forbidden_access")
        )
        assert log is not None
        assert log.operator_id == seed["user_ids"]["member_a"]
        assert log.after_json["actual_role"] == "member"


def test_leader_is_read_only(client, seed, login):
    headers = login("leader")
    response = client.post(
        "/api/member/report/draft",
        json={"week_id": seed["week1_id"], "done": ["越权写入"]},
        headers=headers,
    )

    assert response.status_code == 403


def test_logout_invalidates_token(client, seed, login):
    headers = login("member_a")
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401

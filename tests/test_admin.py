"""系统管理员只读看板接口测试。"""


def test_admin_can_list_users(client, seed, login):
    response = client.get("/api/admin/users", headers=login("admin"))

    assert response.status_code == 200
    users = response.json()
    assert len(users) == 10

    by_username = {user["username"]: user for user in users}
    assert by_username["member_a"]["role"] == "member"
    assert by_username["member_a"]["dept_name"] == "心内科"
    assert by_username["director"]["role"] == "director"
    assert by_username["director"]["dept_name"] == "心内科"
    assert by_username["leader"]["role"] == "leader"
    assert by_username["leader"]["dept_name"] is None
    assert by_username["admin"]["role"] == "admin"
    assert by_username["admin"]["dept_name"] is None


def test_admin_can_read_weeks_and_departments(client, seed, login):
    headers = login("admin")

    weeks = client.get("/api/weeks", headers=headers)
    departments = client.get("/api/departments", headers=headers)

    assert weeks.status_code == 200
    assert [week["week_no"] for week in weeks.json()] == [2, 1]
    assert departments.status_code == 200
    assert {item["name"] for item in departments.json()} == {"心内科", "骨科"}


def test_non_admin_cannot_list_users(client, seed, login):
    for username in ("member_a", "director", "leader"):
        response = client.get("/api/admin/users", headers=login(username))
        assert response.status_code == 403
        assert response.json()["code"] == "forbidden"


def test_admin_users_requires_login(client, seed):
    assert client.get("/api/admin/users").status_code == 401


def test_admin_can_create_and_update_user(client, seed, login):
    headers = login("admin")

    created = client.post(
        "/api/admin/users",
        json={
            "username": "member_f",
            "name": "周医生",
            "role": "member",
            "dept_id": seed["dept1_id"],
            "password": "demo123",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "周医生"
    assert body["role"] == "member"
    assert body["dept_name"] == "心内科"

    duplicate = client.post(
        "/api/admin/users",
        json={
            "username": "member_f",
            "name": "重复账号",
            "role": "member",
            "dept_id": seed["dept1_id"],
            "password": "demo123",
        },
        headers=headers,
    )
    assert duplicate.status_code == 409

    missing_dept = client.post(
        "/api/admin/users",
        json={
            "username": "member_g",
            "name": "吴医生",
            "role": "member",
            "password": "demo123",
        },
        headers=headers,
    )
    assert missing_dept.status_code == 422

    updated = client.put(
        f"/api/admin/users/{body['id']}",
        json={
            "name": "周主任",
            "role": "director",
            "dept_id": seed["dept1_id"],
            "password": "newpass123",
        },
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "周主任"
    assert updated.json()["role"] == "director"

    relogin = client.post(
        "/api/auth/login", json={"username": "member_f", "password": "newpass123"}
    )
    assert relogin.status_code == 200

    update_without_password = client.put(
        f"/api/admin/users/{body['id']}",
        json={
            "name": "周主任（无密码变更）",
            "role": "director",
            "dept_id": seed["dept1_id"],
        },
        headers=headers,
    )
    assert update_without_password.status_code == 200
    assert update_without_password.json()["name"] == "周主任（无密码变更）"


def test_admin_can_create_department(client, seed, login):
    headers = login("admin")

    created = client.post(
        "/api/admin/departments", json={"name": "儿科"}, headers=headers
    )
    assert created.status_code == 201
    assert created.json()["name"] == "儿科"

    duplicate = client.post(
        "/api/admin/departments", json={"name": "儿科"}, headers=headers
    )
    assert duplicate.status_code == 409

    departments = client.get("/api/departments", headers=headers).json()
    assert "儿科" in {item["name"] for item in departments}


def test_admin_can_create_week_and_update_deadline(client, seed, login):
    headers = login("admin")

    created = client.post(
        "/api/admin/weeks",
        json={
            "week_no": 3,
            "start_date": "2026-11-02",
            "end_date": "2026-11-08",
            "deadline": "2026-11-10T23:59:00",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    week = created.json()
    assert week["week_no"] == 3

    duplicate = client.post(
        "/api/admin/weeks",
        json={
            "week_no": 3,
            "start_date": "2026-11-02",
            "end_date": "2026-11-08",
            "deadline": "2026-11-10T23:59:00",
        },
        headers=headers,
    )
    assert duplicate.status_code == 409

    bad_dates = client.post(
        "/api/admin/weeks",
        json={
            "week_no": 4,
            "start_date": "2026-11-08",
            "end_date": "2026-11-02",
            "deadline": "2026-11-10T23:59:00",
        },
        headers=headers,
    )
    assert bad_dates.status_code == 422

    deadline_before_end = client.post(
        "/api/admin/weeks",
        json={
            "week_no": 4,
            "start_date": "2026-11-09",
            "end_date": "2026-11-15",
            "deadline": "2026-11-10T23:59:00",
        },
        headers=headers,
    )
    assert deadline_before_end.status_code == 422

    updated = client.put(
        f"/api/admin/weeks/{week['id']}/deadline",
        json={"deadline": "2026-11-11T23:59:00"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["deadline"].startswith("2026-11-11T23:59")

    invalid_update = client.put(
        f"/api/admin/weeks/{week['id']}/deadline",
        json={"deadline": "2026-11-01T23:59:00"},
        headers=headers,
    )
    assert invalid_update.status_code == 422

    missing = client.put(
        "/api/admin/weeks/999999/deadline",
        json={"deadline": "2026-11-11T23:59:00"},
        headers=headers,
    )
    assert missing.status_code == 404


def test_mutations_are_admin_only(client, seed, login):
    headers = login("director")

    assert (
        client.post(
            "/api/admin/users",
            json={
                "username": "member_x2",
                "name": "越权用户",
                "role": "member",
                "dept_id": seed["dept1_id"],
                "password": "demo123",
            },
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/admin/departments", json={"name": "越权科室"}, headers=headers
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/admin/weeks",
            json={
                "week_no": 9,
                "start_date": "2026-12-01",
                "end_date": "2026-12-07",
                "deadline": "2026-12-08T23:59:00",
            },
            headers=headers,
        ).status_code
        == 403
    )

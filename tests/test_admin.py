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

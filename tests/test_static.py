"""静态页面与挂载测试。"""


def test_index_page_is_served_at_root(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    assert "智能周报系统" in body
    assert "/static/app.js?v=" in body
    assert "/static/style.css?v=" in body
    assert 'data-username="director"' in body
    assert 'id="director-week" data-week-select data-default-week="previous"' in body
    for element_id in (
        "engine-switch",
        "member-save",
        "member-submit",
        "director-items",
        "add-item-btn",
        "director-checked",
        "director-risks",
        "trace-badges",
        "leader-week",
        "leader-dept",
        "leader-reports",
        "modal-reason",
    ):
        assert f'id="{element_id}"' in body


def test_static_assets_are_served(client):
    css = client.get("/static/style.css")
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]

    js = client.get("/static/app.js")
    assert js.status_code == 200
    assert "javascript" in js.headers["content-type"]
    assert "swr_token" in js.text
    assert 'select.dataset.defaultWeek === "previous"' in js.text
    assert "index = preferPrevious && state.weeks.length > 1 ? 1 : 0" in js.text
    assert "function applyDirectorDefaultWeek()" in js.text
    assert "applyDirectorDefaultWeek();" in js.text
    assert "state.weeks.length > 1 ? 1 : 0" in js.text


def test_static_responses_are_not_cached(client):
    for path in ("/", "/static/app.js", "/static/style.css"):
        response = client.get(path)
        assert response.status_code == 200
        assert "no-store" in response.headers.get("cache-control", "")


def test_health_and_docs_still_work(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/docs").status_code == 200


def test_departments_endpoint_for_leader_filter(client, seed, login):
    response = client.get("/api/departments", headers=login("leader"))

    assert response.status_code == 200
    assert {item["name"] for item in response.json()} == {"心内科", "骨科"}

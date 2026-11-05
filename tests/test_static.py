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
    assert 'id="return-preview"' in body
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
        "member-history-btn",
        "director-history-btn",
        "audit-backdrop",
        "audit-list",
        "admin-users-body",
        "admin-depts-body",
        "admin-weeks-body",
        "admin-user-backdrop",
        "admin-dept-backdrop",
        "admin-week-backdrop",
        "admin-deadline-backdrop",
    ):
        assert f'id="{element_id}"' in body
    assert 'id="track-keyword"' not in body
    assert "+ 手动补充条目" in body


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
    assert "/api/director/member-report/" in js.text
    assert "function renderReturnPreview(report)" in js.text
    assert 'class="issue-source">来源：' in js.text
    assert "item.source_names" in js.text
    assert "/api/director/track-item" in js.text
    assert "function toggleItemTrack(index)" in js.text
    assert "function trackInlineHtml()" in js.text
    assert "function extractTrackKeyword(content)" in js.text
    assert "data-track-item" in js.text
    assert "未推进" in js.text
    assert "/api/admin/users" in js.text
    assert "function loadAdminView()" in js.text
    assert "function submitAdminUser()" in js.text
    assert "function submitAdminDept()" in js.text
    assert "function submitAdminWeek()" in js.text
    assert "function submitAdminDeadline()" in js.text
    assert (
        'const RETURNABLE_DEPT_STATUSES = ["已汇总", "已定稿", "已上报", "已退回"]'
        in js.text
    )
    assert "RETURNABLE_DEPT_STATUSES.includes" in js.text
    assert "↑ 上移" in js.text
    assert "↓ 下移" in js.text
    assert "function moveDirectorItem(index, offset)" in js.text
    assert 'source_names: ["主任补充"]' in js.text
    assert "function populateLeaderDeptOptions()" in js.text
    assert "/api/departments" in js.text
    assert '$("#leader-dept").addEventListener("change", loadLeaderView)' in js.text
    assert "function openAuditModal(" in js.text
    assert "function renderAuditTimeline(events)" in js.text
    assert "function auditItemsDiff(beforeItems, afterItems)" in js.text
    assert "function auditMemberContentHtml(data)" in js.text
    assert "展开查看详情" in js.text
    assert "data-audit-extra" in js.text
    assert "AUDIT_ACTION_LABELS" in js.text
    assert 'openAuditModal(\n        "member_report"' in js.text or '"member_report",' in js.text
    assert '"dept_report",' in js.text


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

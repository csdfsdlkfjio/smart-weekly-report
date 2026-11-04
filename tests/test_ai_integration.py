"""AI 汇总链路集成测试：A1 归并、A3 校验、A4 风险与 rule trace。"""

from app.seed import seed_demo_data


def _aggregate(client, headers, week_id, engine_switch="rule"):
    response = client.post(
        "/api/director/aggregate",
        json={"week_id": week_id, "engine_switch": engine_switch},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_week1_aggregate_merges_nursing_items_with_rule_trace(client, session_factory, login):
    seed = seed_demo_data(session_factory())
    headers = login("director")

    body = _aggregate(client, headers, seed["week_ids"][1])

    # A1：近义重复合并为一条，来源包含 A、B 两人
    merged_nursing = [
        item
        for item in body["items"]
        if item["category"] == "done"
        and "张医生" in item["source_names"]
        and "李医生" in item["source_names"]
    ]
    assert len(merged_nursing) == 1
    assert "护理质控" in merged_nursing[0]["content"]
    assert set(merged_nursing[0]["source_user_ids"]) == {
        seed["user_ids"]["member_a"],
        seed["user_ids"]["member_b"],
    }

    # 引擎 trace：全部规则通道
    assert body["engine_trace"]
    assert {trace["agent"] for trace in body["engine_trace"]} == {
        "merger",
        "validator",
        "summarizer",
        "risk",
    }
    assert all(trace["engine"] == "rule" for trace in body["engine_trace"])

    # A3：member_c 的空泛表述被识别
    vague_checked = [
        item
        for item in body["checked"]
        if "日常工作正常开展" in item["content"] or "继续推进相关工作" in item["content"]
    ]
    assert vague_checked
    assert any("空泛" in issue for item in vague_checked for issue in item["issues"])

    # A2：摘要为第三人称且不超过 150 字
    assert body["summary"]
    assert len(body["summary"]) <= 150
    assert "我们" not in body["summary"]

    # trace 通过 meta_json 持久化，重新拉取仍可展示
    persisted = client.get(
        "/api/director/dept-report",
        params={"week_id": seed["week_ids"][1]},
        headers=headers,
    )
    assert persisted.status_code == 200
    assert persisted.json()["engine_trace"] == body["engine_trace"]
    assert persisted.json()["risks"] == body["risks"]


def test_week2_aggregate_reports_missing_member_and_cross_week_risks(client, session_factory, login):
    seed = seed_demo_data(session_factory())
    headers = login("director")

    body = _aggregate(client, headers, seed["week_ids"][2])
    risks = body["risks"]

    missing = [
        risk
        for risk in risks
        if risk["type"] == "missing_submission" and risk["username"] == "member_d"
    ]
    assert missing, "A4 应提示 member_d 第 2 周未提交"
    assert missing[0]["user_id"] == seed["user_ids"]["member_d"]

    unclosed = [
        risk
        for risk in risks
        if risk["type"] == "unclosed_coord" and "协调设备科维修监护仪" in risk["detail"]
    ]
    assert unclosed, "A4 应提示 A 的协调事项连续两周未闭环"

    stale = [
        risk
        for risk in risks
        if risk["type"] == "stale_plan" and "推进电子病历优化" in risk["detail"]
    ]
    assert stale, "A4 应提示 E 的计划事项连续两周未推进"

    assert all(trace["engine"] == "rule" for trace in body["engine_trace"])


def test_explicit_llm_switch_falls_back_to_rule_without_key(client, session_factory, login):
    seed = seed_demo_data(session_factory())
    headers = login("director")

    body = _aggregate(client, headers, seed["week_ids"][1], engine_switch="llm")

    assert all(trace["engine"] == "rule" for trace in body["engine_trace"])
    llm_agents = {
        trace["agent"]: trace for trace in body["engine_trace"] if trace["agent"] != "risk"
    }
    assert set(llm_agents) == {"merger", "validator", "summarizer"}
    assert all(trace["status"] == "degraded" for trace in llm_agents.values())
    assert all("未配置" in trace["detail"] or "降级" in trace["detail"] for trace in llm_agents.values())
    assert body["items"]
    assert body["summary"]

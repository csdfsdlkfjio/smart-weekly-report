"""Agent 规则通道与 LangGraph 编排单元测试。"""

from app.agents.merger import MergerAgent, text_similarity
from app.agents.risk import RiskAgent
from app.agents.summarizer import SummarizerAgent
from app.agents.validator import ValidatorAgent
from app.services.ai_service import run_aggregate


def test_merger_merges_near_duplicate_and_unions_sources():
    raw_items = [
        {"user_id": 1, "user_name": "张医生", "category": "done", "content": "完成护理质控检查"},
        {"user_id": 2, "user_name": "李医生", "category": "done", "content": "护理质控自查已完成"},
        {"user_id": 3, "user_name": "王医生", "category": "done", "content": "完成药品盘点"},
    ]

    merged = MergerAgent().run_rule(raw_items)
    done_items = [item for item in merged if item["category"] == "done"]

    assert text_similarity("完成护理质控检查", "护理质控自查已完成") >= 0.6
    assert len(done_items) == 2
    nursing = next(item for item in done_items if "质控" in item["content"])
    assert nursing["source_user_ids"] == [1, 2]
    assert nursing["source_names"] == ["张医生", "李医生"]

    assert [item["sort_order"] for item in merged] == list(range(len(merged)))


def test_merger_keeps_unrelated_items_separate():
    raw_items = [
        {"user_id": 1, "user_name": "张医生", "category": "done", "content": "完成护理质控检查"},
        {"user_id": 2, "user_name": "李医生", "category": "done", "content": "整理出院病历 30 份"},
    ]

    merged = MergerAgent().run_rule(raw_items)

    assert len(merged) == 2


def test_merger_filters_vague_items_but_returns_them_for_validation():
    raw_items = [
        {"user_id": 1, "user_name": "张医生", "category": "done", "content": "完成护理质控检查 3 次"},
        {"user_id": 3, "user_name": "王医生", "category": "done", "content": "日常工作正常开展"},
        {"user_id": 3, "user_name": "王医生", "category": "plan", "content": "继续推进相关工作"},
    ]

    result = MergerAgent().run_rule_detailed(raw_items)

    assert [item["content"] for item in result["items"]] == ["完成护理质控检查 3 次"]
    assert {item["content"] for item in result["filtered"]} == {
        "日常工作正常开展",
        "继续推进相关工作",
    }
    assert all(item["source_names"] == ["王医生"] for item in result["filtered"])


def test_merger_merges_spot_check_and_self_check_variants():
    raw_items = [
        {"user_id": 1, "user_name": "张医生", "category": "done", "content": "完成护理质控抽查 3 次"},
        {"user_id": 2, "user_name": "李医生", "category": "done", "content": "护理质控自查已完成"},
    ]

    assert text_similarity(raw_items[0]["content"], raw_items[1]["content"]) >= 0.6
    merged = MergerAgent().run_rule(raw_items)

    assert len(merged) == 1
    assert merged[0]["source_user_ids"] == [1, 2]
    assert merged[0]["source_names"] == ["张医生", "李医生"]
    assert merged[0]["content"] == "完成护理质控检查（张医生 3 次，李医生自查）"


def test_merger_preserves_conflicting_numbers_per_source():
    raw_items = [
        {"user_id": 1, "user_name": "张医生", "category": "done", "content": "完成护理质控抽查 3 次"},
        {"user_id": 2, "user_name": "李医生", "category": "done", "content": "完成护理质控自查 4 次"},
    ]

    merged = MergerAgent().run_rule(raw_items)

    assert len(merged) == 1
    assert merged[0]["content"] == "完成护理质控检查（张医生 3 次，李医生 4 次）"


def test_validator_flags_vague_expressions_and_keeps_sources():
    merged = [
        {
            "id": "1",
            "category": "done",
            "content": "日常工作正常开展",
            "source_user_ids": [3],
            "source_names": ["王医生"],
        },
        {
            "id": "2",
            "category": "done",
            "content": "完成护理质控检查 3 次",
            "source_user_ids": [1],
            "source_names": ["张医生"],
        },
    ]

    checked = ValidatorAgent().run_rule(merged)

    assert len(checked) == 1
    assert checked[0]["item_id"] == "1"
    assert checked[0]["source_user_ids"] == [3]
    assert checked[0]["source_names"] == ["王医生"]
    assert any("空泛" in issue for issue in checked[0]["issues"])
    assert checked[0]["suggestions"]


def test_summarizer_is_third_person_and_under_150_chars():
    merged = [
        {"category": "done", "content": "完成护理质控检查"},
        {"category": "done", "content": "组织业务学习 2 次"},
        {"category": "plan", "content": "开展护理技能培训"},
        {"category": "coord", "content": "协调设备科维修监护仪"},
    ]

    summary = SummarizerAgent().run_rule(merged)

    assert len(summary) <= 150
    assert "我们" not in summary
    assert summary.startswith("本周科室完成")


def test_risk_agent_detects_missing_and_cross_week_risks():
    context = {
        "week_no": 2,
        "members": [
            {"user_id": 1, "username": "member_a", "name": "张医生", "submitted": True},
            {"user_id": 4, "username": "member_d", "name": "赵医生", "submitted": False},
        ],
        "current_reports": [
            {
                "user_id": 1,
                "username": "member_a",
                "name": "张医生",
                "done": ["完成护理质控抽查 3 次"],
                "plan": ["开展护理技能培训"],
                "issue": [],
                "coord": ["协调设备科维修监护仪"],
            }
        ],
        "previous_reports": [
            {
                "user_id": 1,
                "username": "member_a",
                "name": "张医生",
                "done": [],
                "plan": ["开展护理技能培训"],
                "issue": [],
                "coord": ["协调设备科维修监护仪"],
            }
        ],
    }

    risks = RiskAgent().run_rule(context)

    assert any(
        risk["type"] == "missing_submission" and risk["username"] == "member_d"
        for risk in risks
    )
    assert any(
        risk["type"] == "unclosed_coord" and "协调设备科维修监护仪" in risk["detail"]
        for risk in risks
    )
    assert any(
        risk["type"] == "stale_plan" and "开展护理技能培训" in risk["detail"]
        for risk in risks
    )


def test_graph_rule_switch_and_llm_fallback_traces():
    raw_items = [
        {"user_id": 1, "user_name": "张医生", "category": "done", "content": "完成护理质控检查"},
        {"user_id": 2, "user_name": "李医生", "category": "done", "content": "护理质控自查已完成"},
    ]
    context = {
        "week_no": 1,
        "members": [
            {"user_id": 1, "username": "member_a", "name": "张医生", "submitted": True},
            {"user_id": 2, "username": "member_b", "name": "李医生", "submitted": True},
        ],
        "current_reports": [],
        "previous_reports": [],
    }

    rule_result = run_aggregate(
        dept_id=1,
        week_id=1,
        raw_items=raw_items,
        risk_context=context,
        engine_switch="rule",
    )
    trace = rule_result["engine_trace"]
    assert {item["agent"] for item in trace} == {"merger", "validator", "summarizer", "risk"}
    assert all(item["engine"] == "rule" for item in trace)
    assert all(item["status"] == "ok" for item in trace)

    # 无 Key 时显式切到 llm，也必须 100% 降级到规则并留下 degraded 记录
    fallback_result = run_aggregate(
        dept_id=1,
        week_id=1,
        raw_items=raw_items,
        risk_context=context,
        engine_switch="llm",
    )
    fallback_trace = fallback_result["engine_trace"]
    assert all(item["engine"] == "rule" for item in fallback_trace)
    assert all(
        item["status"] == "degraded"
        for item in fallback_trace
        if item["agent"] != "risk"
    )
    assert all("降级" in item["detail"] for item in fallback_trace if item["agent"] == "merger")
    assert fallback_result["merged"] and fallback_result["summary"]


def test_graph_filters_vague_from_merged_but_keeps_a3_record():
    raw_items = [
        {"user_id": 1, "user_name": "张医生", "category": "done", "content": "完成护理质控检查 3 次"},
        {"user_id": 3, "user_name": "王医生", "category": "done", "content": "日常工作正常开展"},
    ]
    context = {
        "week_no": 1,
        "members": [
            {"user_id": 1, "username": "member_a", "name": "张医生", "submitted": True},
            {"user_id": 3, "username": "member_c", "name": "王医生", "submitted": True},
        ],
        "current_reports": [],
        "previous_reports": [],
    }

    result = run_aggregate(
        dept_id=1,
        week_id=1,
        raw_items=raw_items,
        risk_context=context,
        engine_switch="rule",
    )

    assert all("日常工作正常开展" not in item["content"] for item in result["merged"])
    assert any("日常工作正常开展" in item["content"] for item in result["checked"])

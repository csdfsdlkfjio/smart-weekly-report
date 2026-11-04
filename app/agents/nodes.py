"""LangGraph 节点：每个节点内部完成 LLM → 规则的降级。"""

from __future__ import annotations

from typing import Any

from app.agents.merger import MergerAgent
from app.agents.risk import RiskAgent
from app.agents.summarizer import SummarizerAgent
from app.agents.validator import ValidatorAgent


def _trace(agent: str, engine: str, status: str, detail: str = "") -> dict[str, str]:
    return {"agent": agent, "engine": engine, "status": status, "detail": detail}


def merger_node(state: dict[str, Any]) -> dict[str, Any]:
    agent = MergerAgent()
    raw_items = state.get("raw_items", [])
    if state.get("engine_switch") == "llm":
        try:
            merged = agent.run_llm(raw_items, timeout=8)
            trace = _trace(agent.name, "llm", "ok", "LLM 归并完成")
        except Exception as exc:  # 节点粒度降级：只影响当前 Agent
            merged = agent.run_rule(raw_items)
            trace = _trace(agent.name, "rule", "degraded", f"LLM 失败自动降级：{exc}")
    else:
        merged = agent.run_rule(raw_items)
        trace = _trace(agent.name, "rule", "ok", "switch=rule")
    return {"merged": merged, "engine_trace": [trace]}


def validator_node(state: dict[str, Any]) -> dict[str, Any]:
    agent = ValidatorAgent()
    merged = state.get("merged", [])
    if state.get("engine_switch") == "llm":
        try:
            checked = agent.run_llm(merged, timeout=8)
            trace = _trace(agent.name, "llm", "ok", "LLM 校验完成")
        except Exception as exc:
            checked = agent.run_rule(merged)
            trace = _trace(agent.name, "rule", "degraded", f"LLM 失败自动降级：{exc}")
    else:
        checked = agent.run_rule(merged)
        trace = _trace(agent.name, "rule", "ok", "switch=rule")
    return {"checked": checked, "engine_trace": [trace]}


def summarizer_node(state: dict[str, Any]) -> dict[str, Any]:
    agent = SummarizerAgent()
    merged = state.get("merged", [])
    checked = state.get("checked", [])
    if state.get("engine_switch") == "llm":
        try:
            summary = agent.run_llm(merged, checked, timeout=8)
            trace = _trace(agent.name, "llm", "ok", "LLM 摘要完成")
        except Exception as exc:
            summary = agent.run_rule(merged, checked)
            trace = _trace(agent.name, "rule", "degraded", f"LLM 失败自动降级：{exc}")
    else:
        summary = agent.run_rule(merged, checked)
        trace = _trace(agent.name, "rule", "ok", "switch=rule")
    return {"summary": summary, "engine_trace": [trace]}


def risk_node(state: dict[str, Any]) -> dict[str, Any]:
    # 风险提示刻意保持纯规则：不调用 LLM，也不参与降级。
    risks = RiskAgent().run_rule(state.get("risk_context", {}))
    return {
        "risks": risks,
        "engine_trace": [_trace("risk", "rule", "ok", "纯规则实现（不调用 LLM）")],
    }

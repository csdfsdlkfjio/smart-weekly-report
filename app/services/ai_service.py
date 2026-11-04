"""AI 服务层：组装 State，调用 LangGraph，返回结构化结果。"""

from __future__ import annotations

from typing import Any

from app.agents.graph import run_workflow


def run_aggregate(
    *,
    dept_id: int,
    week_id: int,
    raw_items: list[dict[str, Any]],
    risk_context: dict[str, Any],
    engine_switch: str = "rule",
) -> dict[str, Any]:
    """执行一次汇总工作流。无 Key 时 engine_switch=llm 也会在节点内降级。"""
    state = {
        "dept_id": dept_id,
        "week_id": week_id,
        "engine_switch": engine_switch,
        "raw_items": raw_items,
        "risk_context": risk_context,
        "engine_trace": [],
    }
    result = run_workflow(state)
    return {
        "merged": result.get("merged", []),
        "checked": result.get("checked", []),
        "summary": result.get("summary", ""),
        "risks": result.get("risks", []),
        "engine_trace": result.get("engine_trace", []),
    }

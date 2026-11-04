"""LangGraph 编排：固定 DAG，risk 与 merger 并行。

    START ──▶ merger ──▶ validator ──▶ summarizer ──▶ END
      └────▶ risk ───────────────────────────────────▶ END

设计取舍：
- 固定 DAG、无条件边、无循环，保证同一输入结果可复现
- 不使用 checkpointer，编排纯内存运行，不引入外部依赖
- 降级发生在节点内部，LangGraph 本身不感知
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.nodes import merger_node, risk_node, summarizer_node, validator_node


class WeekReportState(TypedDict, total=False):
    dept_id: int
    week_id: int
    engine_switch: str  # "llm" | "rule"
    raw_items: list[dict[str, Any]]
    risk_context: dict[str, Any]
    merged: list[dict[str, Any]]
    checked: list[dict[str, Any]]
    summary: str
    risks: list[dict[str, Any]]
    engine_trace: Annotated[list[dict[str, str]], operator.add]


def build_graph():
    graph = StateGraph(WeekReportState)
    graph.add_node("merger", merger_node)
    graph.add_node("validator", validator_node)
    graph.add_node("summarizer", summarizer_node)
    graph.add_node("risk", risk_node)

    graph.add_edge(START, "merger")
    graph.add_edge(START, "risk")  # risk 只读原始数据，与 merger 并行
    graph.add_edge("merger", "validator")
    graph.add_edge("validator", "summarizer")
    graph.add_edge("summarizer", END)
    graph.add_edge("risk", END)

    return graph.compile()


# 编译一次复用；无 checkpointer，纯内存运行
_COMPILED_GRAPH = build_graph()


def run_workflow(state: WeekReportState) -> WeekReportState:
    return _COMPILED_GRAPH.invoke(state)


def invoke_raw(**kwargs: Any) -> dict[str, Any]:
    """便捷入口，便于测试与外部调用。"""
    return run_workflow(kwargs)  # type: ignore[arg-type]

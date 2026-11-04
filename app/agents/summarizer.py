"""A2 摘要生成（规则通道）。

模板化生成 ≤150 字的科室周报概述，使用第三人称公文语体。
"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent

MAX_SUMMARY_LENGTH = 150


def _contents(merged: list[dict[str, Any]], category: str, limit: int) -> list[str]:
    values = [
        str(item.get("content", "")).strip().rstrip("。；;，,.")
        for item in merged
        if item.get("category") == category and str(item.get("content", "")).strip()
    ]
    return list(dict.fromkeys(values))[:limit]


class SummarizerAgent(BaseAgent):
    name = "summarizer"

    def run_rule(
        self,
        merged: list[dict[str, Any]],
        checked: list[dict[str, Any]] | None = None,
    ) -> str:
        done_all = _contents(merged, "done", 10_000)
        done = done_all[:3]
        plan = _contents(merged, "plan", 2)
        coord = _contents(merged, "coord", 2)

        parts = [f"本周科室完成 {len(done_all)} 项工作"]
        if done:
            parts.append("完成事项包括：" + "；".join(done))
        if plan:
            parts.append("下周计划：" + "；".join(plan))
        if coord:
            parts.append("需协调事项：" + "；".join(coord))

        # 避免“需协调协调…”“下周计划推进开展…”这类模板前缀与条目动词重复
        summary = "。".join(parts).replace("我们", "科室") + "。"
        if len(summary) > MAX_SUMMARY_LENGTH:
            summary = summary[: MAX_SUMMARY_LENGTH - 1] + "。"
        return summary

    def run_llm(
        self,
        merged: list[dict[str, Any]],
        checked: list[dict[str, Any]] | None = None,
        timeout: int = 8,
    ) -> str:
        return super().run_llm(merged, checked, timeout=timeout)

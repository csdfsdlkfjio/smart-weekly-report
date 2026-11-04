"""A4 风险提示（纯规则，不调用 LLM）。

输入上下文由业务层预先查库组装，Agent 本身不依赖数据库，便于单测：
- members: 本科室全部成员及本周是否已提交
- current_reports / previous_reports: 本周与上一周的已提交内容
"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent
from app.agents.merger import text_similarity

SIMILARITY_THRESHOLD = 0.6


def _matches(content: str, candidates: list[str]) -> bool:
    return any(text_similarity(content, candidate) >= SIMILARITY_THRESHOLD for candidate in candidates)


class RiskAgent(BaseAgent):
    name = "risk"

    def run_rule(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        risks: list[dict[str, Any]] = []
        week_no = context.get("week_no", "")
        members = context.get("members", [])
        current_reports = context.get("current_reports", [])
        previous_reports = context.get("previous_reports", [])

        # 1) 未提交人员
        for member in members:
            if member.get("submitted"):
                continue
            risks.append(
                {
                    "type": "missing_submission",
                    "level": "high",
                    "user_id": member.get("user_id"),
                    "username": member.get("username"),
                    "user_name": member.get("name"),
                    "detail": f"第 {week_no} 周未提交周报",
                }
            )

        current_by_user = {report.get("user_id"): report for report in current_reports}
        seen: set[tuple[str, int, str]] = set()

        # 2) 跨周风险：只比较本周已提交成员，避免与“未提交”重复告警
        for previous in previous_reports:
            user_id = previous.get("user_id")
            current = current_by_user.get(user_id)
            if current is None:
                continue

            current_done = [str(value) for value in current.get("done", [])]
            current_plan = [str(value) for value in current.get("plan", [])]
            username = current.get("username")
            user_name = current.get("name")

            # 协调事项超过一周仍未出现在完成事项中
            for content in previous.get("coord", []):
                content = str(content).strip()
                if not content or _matches(content, current_done):
                    continue
                key = ("unclosed_coord", user_id, content)
                if key in seen:
                    continue
                seen.add(key)
                risks.append(
                    {
                        "type": "unclosed_coord",
                        "level": "medium",
                        "user_id": user_id,
                        "username": username,
                        "user_name": user_name,
                        "detail": f"协调事项“{content}”超过一周未闭环",
                    }
                )

            # 连续两周停留在计划中、未进入完成事项
            for content in previous.get("plan", []):
                content = str(content).strip()
                if not content or _matches(content, current_done):
                    continue
                if not _matches(content, current_plan):
                    continue
                key = ("stale_plan", user_id, content)
                if key in seen:
                    continue
                seen.add(key)
                risks.append(
                    {
                        "type": "stale_plan",
                        "level": "medium",
                        "user_id": user_id,
                        "username": username,
                        "user_name": user_name,
                        "detail": f"计划事项“{content}”连续两周未推进",
                    }
                )

        return risks

    def run_llm(self, context: dict[str, Any], timeout: int = 8) -> list[dict[str, Any]]:
        # 风险提示刻意保持纯规则：低成本、可解释、零降级负担
        return self.run_rule(context)

"""A3 规范校验（规则通道）。

基于空泛词词典 + 量化检测，识别“日常工作正常开展”这类表述并给出建议。
"""

from __future__ import annotations

import re
from typing import Any

from app.agents.base import BaseAgent
from app.agents.vague import matched_vague_word

_QUANTITY_RE = re.compile(
    r"\d+(\.\d+)?%?|[一二三四五六七八九十百千万]+次|[一二三四五六七八九十百千万]+人"
)


class ValidatorAgent(BaseAgent):
    name = "validator"

    def run_rule(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        checked: list[dict[str, Any]] = []
        for item in items:
            content = str(item.get("content", "")).strip()
            category = str(item.get("category", ""))
            if not content:
                continue

            issues: list[str] = []
            vague_word = matched_vague_word(content)
            if vague_word:
                issues.append(f"表述空泛：{vague_word}")

            if category == "done" and not _QUANTITY_RE.search(content):
                issues.append("缺少量化数据")

            if not issues:
                continue

            checked.append(
                {
                    "item_id": item.get("id", ""),
                    "category": category,
                    "content": content,
                    "issues": issues,
                    "suggestions": ["请补充数量、完成率或具体结果，避免使用空泛表述"],
                }
            )
        return checked

    def run_llm(self, items: list[dict[str, Any]], timeout: int = 8) -> list[dict[str, Any]]:
        return super().run_llm(items, timeout=timeout)

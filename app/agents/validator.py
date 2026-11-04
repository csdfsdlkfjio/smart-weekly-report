"""A3 规范校验（规则通道）。

基于空泛词词典 + 量化检测，识别“日常工作正常开展”这类表述并给出建议。
"""

from __future__ import annotations

import json
import re
from typing import Any

from app import config
from app.agents.base import BaseAgent

_DEFAULT_VAGUE_WORDS = [
    "日常工作正常开展",
    "正常开展",
    "继续推进相关工作",
    "继续推进",
    "按计划推进",
    "有序推进",
    "稳步推进",
    "持续跟进",
]

_QUANTITY_RE = re.compile(r"\d+(\.\d+)?%?|[一二三四五六七八九十百千万]+次|[一二三四五六七八九十百千万]+人")


def _load_vague_words() -> list[str]:
    path = config.DATA_DIR / "vague_words.json"
    if path.exists():
        try:
            words = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(words, list) and words:
                return [str(word) for word in words]
        except (OSError, json.JSONDecodeError):
            pass
    return _DEFAULT_VAGUE_WORDS


VAGUE_WORDS = _load_vague_words()


class ValidatorAgent(BaseAgent):
    name = "validator"

    def run_rule(self, merged: list[dict[str, Any]]) -> list[dict[str, Any]]:
        checked: list[dict[str, Any]] = []
        for item in merged:
            content = str(item.get("content", "")).strip()
            category = str(item.get("category", ""))
            if not content:
                continue

            issues: list[str] = []
            hits = [word for word in VAGUE_WORDS if word in content]
            if hits:
                # 只保留最长的命中，避免“日常工作正常开展/正常开展”重复提示
                hits.sort(key=len, reverse=True)
                issues.append(f"表述空泛：{hits[0]}")

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

    def run_llm(self, merged: list[dict[str, Any]], timeout: int = 8) -> list[dict[str, Any]]:
        return super().run_llm(merged, timeout=timeout)

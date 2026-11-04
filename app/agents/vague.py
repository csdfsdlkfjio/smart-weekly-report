"""空泛表述词库与统一匹配入口。

MergerAgent 用它把空泛条目从最终归并结果中剔除；
ValidatorAgent 用它生成 A3 校验建议。
"""

from __future__ import annotations

import json

from app import config

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


def matched_vague_word(text: str) -> str | None:
    """返回命中的最长空泛词；未命中返回 None。"""
    hits = [word for word in VAGUE_WORDS if word in str(text)]
    return max(hits, key=len) if hits else None


def is_vague(text: str) -> bool:
    return matched_vague_word(text) is not None

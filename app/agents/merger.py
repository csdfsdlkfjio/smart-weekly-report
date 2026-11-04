"""A1 智能归并（规则通道）。

流程：jieba 分词 → 停用词过滤 → 同义词归一 → Jaccard 相似度 →
超过阈值合并 → 来源人员取并集。相似度阈值默认 0.6，可通过
环境变量 MERGE_THRESHOLD 调整。
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

import jieba

from app import config
from app.agents.base import BaseAgent
from app.agents.vague import is_vague

jieba.setLogLevel(logging.WARNING)
jieba.initialize()

CATEGORY_ORDER = ("done", "plan", "issue", "coord")

STOPWORDS = {
    "的",
    "了",
    "已",
    "并",
    "和",
    "及",
    "与",
    "在",
    "对",
    "等",
    "相关",
    "工作",
}

_PUNCT_RE = re.compile(r"[\s，。；、,.!?！？:：;\"'“”‘’（）()\[\]【】]+")

_DEFAULT_SYNONYMS = {
    "检查": ["检查", "自查", "核查", "巡检", "抽查"],
    "完成": ["完成", "已完成", "办结"],
    "培训": ["培训", "学习", "讲座"],
    "优化": ["优化", "改进", "完善"],
    "协调": ["协调", "沟通", "对接"],
    "推进": ["推进", "推动", "落实"],
}


def _load_synonyms() -> dict[str, str]:
    """加载 同义词 -> 规范词 的映射。"""
    raw = _DEFAULT_SYNONYMS
    path = config.DATA_DIR / "synonyms.json"
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = _DEFAULT_SYNONYMS

    mapping: dict[str, str] = {}
    for canonical, variants in raw.items():
        mapping[canonical] = canonical
        for variant in variants:
            mapping[variant] = canonical
    return mapping


_SYNONYMS = _load_synonyms()


def tokens(text: str) -> list[str]:
    """分词并归一化；返回去重后的词列表。"""
    cleaned = _PUNCT_RE.sub("", str(text))
    if not cleaned:
        return []
    result: list[str] = []
    for token in jieba.lcut(cleaned):
        token = token.strip()
        if not token or token in STOPWORDS:
            continue
        token = _SYNONYMS.get(token, token)
        result.append(token)
    return list(dict.fromkeys(result))


def text_similarity(left: str, right: str) -> float:
    """Jaccard 相似度，范围 0~1。

    额外规则：若一条的词集完全包含另一条（长句包含短句），直接视为高度相似。
    例如“完成护理质控抽查 3 次”包含“护理质控自查已完成”的核心词。
    """
    left_tokens = set(tokens(left))
    right_tokens = set(tokens(right))
    if not left_tokens or not right_tokens:
        return 1.0 if str(left).strip() == str(right).strip() else 0.0
    if left_tokens <= right_tokens or right_tokens <= left_tokens:
        return 1.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def split_vague_items(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """把空泛条目从展示结果中分离，供 A3 校验留痕使用。"""
    kept: list[dict[str, Any]] = []
    filtered: list[dict[str, Any]] = []
    for item in items:
        if is_vague(str(item.get("content", ""))):
            filtered.append(item)
        else:
            kept.append(item)
    return kept, filtered


class MergerAgent(BaseAgent):
    name = "merger"

    def run_rule(self, raw_items: list[dict[str, Any]], threshold: float | None = None) -> list[dict[str, Any]]:
        return self.run_rule_detailed(raw_items, threshold)["items"]

    def run_rule_detailed(
        self,
        raw_items: list[dict[str, Any]],
        threshold: float | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """归并并在 Merger 阶段剔除空泛条目。

        返回 {"items": 展示用归并结果, "filtered": 被剔除的空泛条目}；
        filtered 会交给 ValidatorAgent 生成 A3 校验记录。
        """
        threshold = config.MERGE_THRESHOLD if threshold is None else threshold
        clusters: dict[str, list[dict[str, Any]]] = {category: [] for category in CATEGORY_ORDER}
        filtered: list[dict[str, Any]] = []

        for raw in raw_items:
            category = str(raw.get("category", ""))
            content = str(raw.get("content", "")).strip()
            if category not in clusters or not content:
                continue

            user_id = int(raw["user_id"])
            user_name = str(raw.get("user_name", user_id))

            # 空泛表述不进入最终展示，但保留下来供 A3 校验留痕
            if is_vague(content):
                filtered.append(
                    {
                        "id": uuid.uuid4().hex,
                        "category": category,
                        "content": content,
                        "source_user_ids": [user_id],
                        "source_names": [user_name],
                        "sort_order": 0,
                        "edited_by": None,
                    }
                )
                continue

            target: dict[str, Any] | None = None
            best_score = 0.0
            for candidate in clusters[category]:
                score = text_similarity(content, candidate["content"])
                if score >= threshold and score > best_score:
                    target = candidate
                    best_score = score

            if target is None:
                clusters[category].append(
                    {
                        "id": uuid.uuid4().hex,
                        "category": category,
                        "content": content,
                        "source_user_ids": [user_id],
                        "source_names": [user_name],
                        "sort_order": 0,
                        "edited_by": None,
                    }
                )
                continue

            target["source_user_ids"] = list(dict.fromkeys(target["source_user_ids"] + [user_id]))
            target["source_names"] = list(dict.fromkeys(target["source_names"] + [user_name]))
            # 保留信息量更大的表述
            if len(content) > len(target["content"]):
                target["content"] = content

        merged: list[dict[str, Any]] = []
        for category in CATEGORY_ORDER:
            for item in clusters[category]:
                item["sort_order"] = len(merged)
                merged.append(item)
        return {"items": merged, "filtered": filtered}

    def run_llm(self, raw_items: list[dict[str, Any]], timeout: int = 8) -> list[dict[str, Any]]:
        return super().run_llm(raw_items, timeout=timeout)

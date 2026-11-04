"""应用配置：全部通过环境变量覆盖，默认值保证单机开箱即用。"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{(DATA_DIR / 'weekly_report.db').as_posix()}"
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "12"))
# 启动时自动灌入演示数据，保证评委启动即见数据；设为 0 可关闭。
AUTO_SEED = os.getenv("AUTO_SEED", "1") == "1"

# 规则归并阈值（Jaccard 相似度）
MERGE_THRESHOLD = float(os.getenv("MERGE_THRESHOLD", "0.6"))

# 大模型通道配置（当前阶段无 Key 时全部走规则引擎）
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

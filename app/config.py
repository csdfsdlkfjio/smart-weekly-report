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

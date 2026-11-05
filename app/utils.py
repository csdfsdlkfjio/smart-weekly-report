"""统一时间工具：全系统使用北京时间（Asia/Shanghai，UTC+8）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# 固定东八区，避免 Windows 环境缺少 zoneinfo/tzdata 依赖
BEIJING_TZ = timezone(timedelta(hours=8))


def now_beijing() -> datetime:
    """返回带时区的北京时间。"""
    return datetime.now(BEIJING_TZ)


def get_now() -> datetime:
    """返回北京时间墙钟值（naive）。

    数据库 DateTime 列不保存时区；统一存储北京时间墙钟值，
    前端展示时按 Asia/Shanghai（+08:00）解析。
    """
    return now_beijing().replace(tzinfo=None)

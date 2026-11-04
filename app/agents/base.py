"""Agent 基类与统一结果契约。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel

from app.agents.llm_client import LLMNotConfigured, llm_configured


class AgentResult(BaseModel):
    """所有 Agent 的统一返回结构。"""

    data: Any
    engine: Literal["llm", "rule"]
    status: Literal["ok", "degraded"]
    detail: str = ""


class BaseAgent(ABC):
    """Agent 对外只有两套实现：LLM 与规则。"""

    name: str = "base"

    @abstractmethod
    def run_rule(self, *args, **kwargs) -> Any:
        """规则通道：必须始终可用，是降级的底线。"""

    def run_llm(self, *args, **kwargs) -> Any:
        """LLM 通道：当前阶段未接入，统一抛异常触发规则降级。"""
        if not llm_configured():
            raise LLMNotConfigured("未配置大模型密钥")
        raise LLMNotConfigured("大模型通道尚未接入，已降级到规则引擎")

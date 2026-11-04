"""大模型通道占位。

当前阶段没有可用的 API Key，所有 Agent 的 LLM 通道都会抛出
`LLMNotConfigured`，由节点捕获后降级到规则实现。
"""

from __future__ import annotations

from app import config


class LLMNotConfigured(RuntimeError):
    """未配置大模型，或 LLM 通道尚未接入。"""


def llm_configured() -> bool:
    return bool(config.LLM_API_KEY.strip())


class LLMClient:
    """预留的 OpenAI 兼容客户端，第二阶段只保留接口。"""

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or config.LLM_API_KEY
        self.base_url = base_url or config.LLM_BASE_URL
        self.model = model or config.LLM_MODEL

    def call_json(self, prompt: str, timeout: int = 8):
        if not self.api_key:
            raise LLMNotConfigured("未配置大模型密钥")
        raise LLMNotConfigured("大模型通道尚未接入，已降级到规则引擎")

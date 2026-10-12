"""LLM 客户端层：统一不同 provider 的接口，返回标准化的 ToolCall。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from config import AgentConfig, ProviderConfig


# ---------------------------------------------------------------------------
# 标准化的响应结构
# ---------------------------------------------------------------------------

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatResponse:
    content: str | None
    tool_calls: list[ToolCall]
    raw: dict[str, Any]
    usage: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# LLM 客户端
# ---------------------------------------------------------------------------

class LLMClient:
    def __init__(self, cfg: AgentConfig):
        self.cfg = cfg
        self.provider: ProviderConfig = cfg.provider_config
        self.client = OpenAI(
            api_key=self.provider.resolve_api_key(),
            base_url=self.provider.base_url,
        )

    # --- 对外主入口 ---
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        max_retries: int = 2,
    ) -> ChatResponse:
        """向 LLM 发送消息并返回标准化响应，带简单重试。"""
        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                return self._chat_once(messages, tools, tool_choice)
            except Exception as e:  # noqa: BLE001
                last_error = e
                if attempt < max_retries:
                    time.sleep(1.5 * (attempt + 1))  # 退避重试
        raise RuntimeError(f"LLM 调用失败（已重试 {max_retries} 次）: {last_error}")

    # --- 单次调用与解析 ---
    def _chat_once(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        tool_choice: str,
    ) -> ChatResponse:
        kwargs: dict[str, Any] = {
            "model": self.provider.model,
            "messages": messages,
            "temperature": 0.0,  # Agent 任务尽量确定性
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        resp = self.client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message

        content = msg.content
        raw_tool_calls = msg.tool_calls or []

        tool_calls = [self._parse_tool_call(tc) for tc in raw_tool_calls]

        usage = {}
        if resp.usage:
            usage = {
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
                "total_tokens": resp.usage.total_tokens,
            }

        return ChatResponse(
            content=content,
            tool_calls=tool_calls,
            raw=resp.model_dump(),
            usage=usage,
        )

    # --- 工具调用参数解析（跨厂商兼容） ---
    @staticmethod
    def _parse_tool_call(raw_tc: Any) -> ToolCall:
        """处理不同 provider 返回 arguments 可能是 str 或 dict 的情况。"""
        arguments = raw_tc.function.arguments
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                # 极端情况：返回了非法 JSON，包一层错误信息
                arguments = {"_raw_arguments": arguments, "_error": "JSON 解析失败"}
        elif arguments is None:
            arguments = {}

        return ToolCall(
            id=raw_tc.id,
            name=raw_tc.function.name,
            arguments=arguments,
        )
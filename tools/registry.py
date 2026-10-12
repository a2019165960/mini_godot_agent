"""工具注册中心：登记工具、提供 schema、安全执行。"""

from __future__ import annotations

from typing import Any, Callable

from config import AgentConfig


class ToolRegistry:
    def __init__(self, cfg: AgentConfig):
        self.cfg = cfg
        self._tools: dict[str, Callable[..., Any]] = {}
        self._schemas: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # 注册
    # ------------------------------------------------------------------
    def register(self, name: str, schema: dict[str, Any], func: Callable[..., Any]) -> None:
        """注册单个工具。schema 需符合 OpenAI Function Calling 格式。"""
        if name in self._tools:
            raise ValueError(f"工具重复注册: {name}")
        self._tools[name] = func
        self._schemas.append(schema)

    def schemas(self) -> list[dict[str, Any]]:
        """返回全部工具 schema，供 LLMClient 使用。"""
        return self._schemas

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------
    def call(self, name: str, arguments: dict[str, Any]) -> str:
        """执行工具，异常不抛出，转为字符串返回给 LLM。"""
        if name not in self._tools:
            return f"工具执行失败：未找到工具 `{name}`"

        try:
            result = self._tools[name](**arguments)
        except TypeError as e:
            # 参数不匹配，通常是 LLM 给错了参数名或数量
            return f"工具执行失败（参数错误）：{e}"
        except Exception as e:  # noqa: BLE001
            return f"工具执行失败（{type(e).__name__}）：{e}"

        return self._truncate(str(result))

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------
    def _truncate(self, text: str) -> str:
        """防止工具输出过长撑爆上下文。"""
        limit = self.cfg.output_limit
        if len(text) <= limit:
            return text
        remain = len(text) - limit
        return text[:limit] + f"\n...[输出过长，已截断 {remain} 字符]"
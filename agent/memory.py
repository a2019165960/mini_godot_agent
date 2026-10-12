"""会话记忆：管理 LLM 的消息历史。"""

from __future__ import annotations

import json

from agent.llm import ToolCall


class Memory:
    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.files_touched: set[str] = set()

    # ------------------------------------------------------------------
    # 写入消息
    # ------------------------------------------------------------------
    def add_system(self, content: str) -> None:
        self.messages.append({"role": "system", "content": content})

    def add_user(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant(self, content: str | None, tool_calls: list[ToolCall] | None = None) -> None:
        """添加 assistant 消息。如果有工具调用，必须按 OpenAI 协议格式编码。"""
        msg: dict = {"role": "assistant", "content": content or ""}
        if tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        # OpenAI 协议要求 arguments 是 JSON 字符串，不是 dict
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }
                for tc in tool_calls
            ]
        self.messages.append(msg)

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        self.messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": content,
            }
        )

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------
    def track_file(self, path: str) -> None:
        """记录被写过的文件，便于最后生成摘要。"""
        self.files_touched.add(path)

    @property
    def message_count(self) -> int:
        return len(self.messages)
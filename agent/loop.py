"""Agent 主循环：Plan → Act → Observe。"""

from __future__ import annotations

from config import AgentConfig
from agent.llm import LLMClient
from agent.memory import Memory
from agent.logger import Logger
from tools.registry import ToolRegistry


SYSTEM_PROMPT = """你是一个专门协助用户开发 Godot 游戏的 Agent。

当前工作区：{workspace}
Godot 版本：4.7.1

你的工作原则：
1. 先规划，再执行。收到任务后，先在心里想清楚步骤，然后逐步调用工具。
2. 不要凭空假设文件内容，用工具读取。不要凭记忆写代码，用工具写文件。
3. 每次修改文件后，尽量运行 Godot 检查来验证是否报错。
4. 遇到错误时，读取错误信息，尝试修复。不要重复同一个失败操作。
5. 所有文件操作都被限制在工作区目录内，路径越界会被拒绝。
6. 完成任务后，用中文简要总结：
   - 创建/修改了哪些文件
   - 运行了哪些验证命令，结果如何
   - 用户接下来可以做什么

不要输出无关的客套话。用简洁、明确的语言。"""


class AgentLoop:
    def __init__(
        self,
        llm: LLMClient,
        registry: ToolRegistry,
        memory: Memory,
        logger: Logger,
        cfg: AgentConfig,
    ):
        self.llm = llm
        self.registry = registry
        self.memory = memory
        self.logger = logger
        self.cfg = cfg

    def run(self, goal: str) -> str:
        # 初始化 system prompt
        self.memory.add_system(SYSTEM_PROMPT.format(workspace=self.cfg.workspace))
        self.memory.add_user(goal)
        self.logger.info(f"目标：{goal}")

        for step in range(1, self.cfg.max_steps + 1):
            self.logger.step(step, "调用 LLM")

            try:
                resp = self.llm.chat(
                    messages=self.memory.messages,
                    tools=self.registry.schemas(),
                )
            except Exception as e:  # noqa: BLE001
                self.logger.error(f"LLM 调用失败：{e}")
                return f"任务中断：LLM 调用失败 - {e}"

            # 情况 A：没有工具调用 → LLM 认为任务完成
            if not resp.tool_calls:
                content = resp.content or "（模型未返回内容）"
                self.logger.info("LLM 认为任务完成")
                self.memory.add_assistant(content)
                return content

            # 情况 B：有工具调用 → 记录下来并逐个执行
            self.memory.add_assistant(resp.content, resp.tool_calls)
            tool_names = ", ".join(tc.name for tc in resp.tool_calls)
            self.logger.step(step, f"调用工具：{tool_names}")

            for call in resp.tool_calls:
                result = self.registry.call(call.name, call.arguments)
                self.memory.add_tool_result(call.id, result)
                self.logger.tool(call.name, call.arguments, result)

                # 顺手记录文件轨迹
                if call.name == "write_file":
                    self.memory.track_file(call.arguments.get("path", "?"))

        msg = f"达到最大步数（{self.cfg.max_steps}），任务未完成。"
        self.logger.error(msg)
        return msg
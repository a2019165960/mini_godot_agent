"""文件系统工具：读写、列目录、建目录，带沙箱校验。"""

from __future__ import annotations

from pathlib import Path

from config import AgentConfig
from agent.safety import resolve_path, SafetyError, truncate
from tools.registry import ToolRegistry


def register_fs_tools(registry: ToolRegistry, cfg: AgentConfig) -> None:
    """将文件系统工具注册到 registry 中。

    使用闭包绑定 cfg，使 LLM 只看到必要的参数（path, content）。
    """
    workspace = cfg.workspace
    output_limit = cfg.output_limit

    # ------------------------------------------------------------------
    # 1. list_files
    # ------------------------------------------------------------------
    def list_files(path: str = ".") -> str:
        try:
            target = resolve_path(workspace, path)
            if not target.exists():
                return f"错误：路径不存在 {path}"
            if target.is_file():
                return f"错误：{path} 是文件，不是目录"

            entries = []
            for entry in target.iterdir():
                # 过滤掉 .agent 内部目录，避免 LLM 看到自身日志和记忆文件
                if entry.name.startswith(".agent"):
                    continue
                suffix = "/" if entry.is_dir() else ""
                entries.append(f"{entry.name}{suffix}")

            return "\n".join(sorted(entries)) if entries else "（空目录）"
        except SafetyError as e:
            return f"安全错误：{e}"

    registry.register(
        name="list_files",
        schema={
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "列出工作区中指定目录下的所有文件和文件夹。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "相对于工作区的目录路径，默认是 '.'",
                        }
                    },
                },
            },
        },
        func=list_files,
    )

    # ------------------------------------------------------------------
    # 2. read_file
    # ------------------------------------------------------------------
    def read_file(path: str) -> str:
        try:
            target = resolve_path(workspace, path)
            if not target.exists():
                return f"错误：文件不存在 {path}"
            if not target.is_file():
                return f"错误：{path} 是目录，不是文件"

            # 防御：限制读取文件的大小（比如 1MB），防止上下文爆炸
            file_size = target.stat().st_size
            if file_size > 1024 * 1024:
                return f"错误：文件过大（{file_size} 字节），拒绝读取"

            content = target.read_text(encoding="utf-8")
            return truncate(content, output_limit)
        except UnicodeDecodeError:
            return f"错误：文件 {path} 不是 UTF-8 编码的文本文件"
        except SafetyError as e:
            return f"安全错误：{e}"

    registry.register(
        name="read_file",
        schema={
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "读取工作区中指定文本文件的内容。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "相对于工作区的文件路径",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
        func=read_file,
    )

    # ------------------------------------------------------------------
    # 3. write_file
    # ------------------------------------------------------------------
    def write_file(path: str, content: str) -> str:
        try:
            target = resolve_path(workspace, path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return f"写入成功：{path}（{len(content)} 字符）"
        except SafetyError as e:
            return f"安全错误：{e}"
        except Exception as e:  # noqa: BLE001
            return f"写入失败：{type(e).__name__}: {e}"

    registry.register(
        name="write_file",
        schema={
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "将内容写入工作区中的指定文件，如果文件不存在会自动创建。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "相对于工作区的文件路径",
                        },
                        "content": {
                            "type": "string",
                            "description": "要写入的文件内容",
                        },
                    },
                    "required": ["path", "content"],
                },
            },
        },
        func=write_file,
    )

    # ------------------------------------------------------------------
    # 4. make_dir
    # ------------------------------------------------------------------
    def make_dir(path: str) -> str:
        try:
            target = resolve_path(workspace, path)
            target.mkdir(parents=True, exist_ok=True)
            return f"创建目录成功：{path}"
        except SafetyError as e:
            return f"安全错误：{e}"

    registry.register(
        name="make_dir",
        schema={
            "type": "function",
            "function": {
                "name": "make_dir",
                "description": "在工作区中创建目录（包含多级目录）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "相对于工作区的目录路径",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
        func=make_dir,
    )
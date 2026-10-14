"""Godot 工具：封装 headless 命令，用于验证和运行项目。"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from config import AgentConfig
from agent.safety import resolve_path, SafetyError, truncate
from tools.registry import ToolRegistry


def _find_godot_bin() -> str:
    """查找 Godot 可执行文件路径。

    优先顺序：
      1. 环境变量 GODOT_BIN
      2. PATH 中的 godot
    """
    env_bin = os.getenv("GODOT_BIN")
    if env_bin:
        return env_bin

    found = shutil.which("godot") or shutil.which("godot4")
    if found:
        return found

    raise FileNotFoundError(
        "找不到 Godot 可执行文件。请设置环境变量 GODOT_BIN 指向 Godot 的 exe 路径，"
        "或把 Godot 加入 PATH。"
    )


def _to_text(value) -> str:
    """把 subprocess 的输出统一转成 str。

    text=True 时是 str；timeout 场景在某些 Python 版本可能给 bytes。
    两种情况都处理。
    """
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "ignore")
    return value


def register_godot_tools(registry: ToolRegistry, cfg: AgentConfig) -> None:
    workspace = cfg.workspace
    output_limit = cfg.output_limit
    timeout = cfg.tool_timeout

    # ------------------------------------------------------------------
    # 1. godot_version
    # ------------------------------------------------------------------
    def godot_version() -> str:
        try:
            godot_bin = _find_godot_bin()
        except FileNotFoundError as e:
            return f"错误：{e}"

        try:
            result = subprocess.run(
                [godot_bin, "--version"],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except subprocess.TimeoutExpired:
            return "错误：godot --version 超时"
        except Exception as e:  # noqa: BLE001
            return f"错误：{type(e).__name__}: {e}"

        out = (result.stdout + result.stderr).strip()
        return f"exit_code={result.returncode}\n{truncate(out, output_limit)}"

    registry.register(
        name="godot_version",
        schema={
            "type": "function",
            "function": {
                "name": "godot_version",
                "description": "查看当前系统上的 Godot 可执行文件版本。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        func=godot_version,
    )

    # ------------------------------------------------------------------
    # 2. godot_check
    # ------------------------------------------------------------------
    def godot_check(project_path: str) -> str:
        """运行 `godot --headless --path <project_path> --quit`，检查导入是否报错。"""
        try:
            target = resolve_path(workspace, project_path)
        except SafetyError as e:
            return f"安全错误：{e}"

        if not target.exists():
            return f"错误：项目路径不存在 {project_path}"
        if not (target / "project.godot").exists():
            return f"错误：{project_path} 下没有 project.godot，不像是 Godot 项目"

        try:
            godot_bin = _find_godot_bin()
        except FileNotFoundError as e:
            return f"错误：{e}"

        cmd = [
            godot_bin,
            "--headless",
            "--path", str(target),
            "--quit",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=workspace,  # 以 workspace 为工作目录
            )
        except subprocess.TimeoutExpired:
            return f"错误：godot_check 超时（>{timeout}s）"
        except Exception as e:  # noqa: BLE001
            return f"错误：{type(e).__name__}: {e}"

        stdout = truncate(result.stdout.strip(), output_limit)
        stderr = truncate(result.stderr.strip(), output_limit)

        return (
            f"exit_code={result.returncode}\n"
            f"--- stdout ---\n{stdout}\n"
            f"--- stderr ---\n{stderr}"
        )

    registry.register(
        name="godot_check",
        schema={
            "type": "function",
            "function": {
                "name": "godot_check",
                "description": (
                    "用 Godot headless 模式导入项目并立即退出，检查项目是否有脚本、"
                    "场景或资源错误。返回退出码和日志。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "project_path": {
                            "type": "string",
                            "description": "相对于工作区的项目根目录路径，如 'demo'",
                        }
                    },
                    "required": ["project_path"],
                },
            },
        },
        func=godot_check,
    )

    # ------------------------------------------------------------------
    # 3. godot_run_scene
    # ------------------------------------------------------------------
    def godot_run_scene(project_path: str, scene: str, seconds: int = 5) -> str:
        """headless 运行指定场景，最多 seconds 秒后强制终止。"""
        try:
            target = resolve_path(workspace, project_path)
        except SafetyError as e:
            return f"安全错误：{e}"

        if not target.exists():
            return f"错误：项目路径不存在 {project_path}"

        try:
            godot_bin = _find_godot_bin()
        except FileNotFoundError as e:
            return f"错误：{e}"

        # scene 参数接受两种形式："main.tscn" 或 "res://main.tscn"
        if scene.startswith("res://"):
            scene_arg = scene
        else:
            scene_arg = f"res://{scene}"

        cmd = [
            godot_bin,
            "--headless",
            "--path", str(target),
            scene_arg,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=seconds,
                cwd=workspace,
            )
            timed_out = False
        except subprocess.TimeoutExpired as e:
            # 场景跑满 seconds 秒是预期行为，不算失败
            # 用 helper 统一处理 str / bytes
            stdout = truncate(_to_text(e.stdout).strip(), output_limit)
            stderr = truncate(_to_text(e.stderr).strip(), output_limit)
            return (
                f"运行结束：达到 {seconds}s 超时（预期行为）\n"
                f"--- stdout ---\n{stdout}\n"
                f"--- stderr ---\n{stderr}"
            )
        except Exception as e:  # noqa: BLE001
            return f"错误：{type(e).__name__}: {e}"

        stdout = truncate(_to_text(result.stdout).strip(), output_limit)
        stderr = truncate(_to_text(result.stderr).strip(), output_limit)
        return (
            f"exit_code={result.returncode}\n"
            f"--- stdout ---\n{stdout}\n"
            f"--- stderr ---\n{stderr}"
        )

    registry.register(
        name="godot_run_scene",
        schema={
            "type": "function",
            "function": {
                "name": "godot_run_scene",
                "description": (
                    "在 headless 模式下运行指定的 Godot 场景，最多运行 seconds 秒。"
                    "适合验证场景能否正常启动、是否在启动时崩溃。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "project_path": {
                            "type": "string",
                            "description": "相对于工作区的项目根目录路径",
                        },
                        "scene": {
                            "type": "string",
                            "description": "场景文件名，如 'main.tscn'",
                        },
                        "seconds": {
                            "type": "integer",
                            "description": "最多运行多少秒，默认 5",
                        },
                    },
                    "required": ["project_path", "scene"],
                },
            },
        },
        func=godot_run_scene,
    )
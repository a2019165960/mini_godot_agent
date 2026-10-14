"""Git 工具：为 Agent 提供自动提交和回滚能力。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from config import AgentConfig
from agent.safety import truncate
from tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# 内部：不暴露给 LLM
# ---------------------------------------------------------------------------

def _git(args: list[str], cwd: Path, timeout: int = 30) -> tuple[int, str, str]:
    """执行 git 命令，返回 (returncode, stdout, stderr)。"""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return -1, "", "找不到 git 命令，请确认 git 已安装并在 PATH 中"
    except subprocess.TimeoutExpired:
        return -1, "", f"git 命令超时（>{timeout}s）"


def ensure_git_repo(workspace: Path) -> str:
    """确保 workspace 是 git 仓库，否则初始化。"""
    if (workspace / ".git").exists():
        return "已存在 git 仓库"

    code, _, err = _git(["init"], workspace)
    if code != 0:
        return f"git init 失败：{err.strip()}"

    # 配置本地身份，避免首次 commit 报错
    _git(["config", "user.email", "agent@local"], workspace)
    _git(["config", "user.name", "MiniAgent"], workspace)

    # 写 .gitignore，排除 Agent 自己的运行时文件
    gitignore = workspace / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(".agent/\n", encoding="utf-8")

    _git(["add", ".gitignore"], workspace)
    _git(["commit", "-m", "chore: init repo"], workspace)

    return "已初始化 git 仓库"


def auto_commit(workspace: Path, message: str) -> str:
    """自动提交当前所有改动。无变化时跳过。"""
    ensure_git_repo(workspace)

    _git(["add", "-A"], workspace)

    # 检查 staged 区是否有变化
    code, _, _ = _git(["diff", "--cached", "--quiet"], workspace)
    if code == 0:
        return "无变化，跳过提交"

    code, out, err = _git(["commit", "-m", message], workspace)
    if code != 0:
        return f"提交失败：{(err or out).strip()}"

    code, hash_out, _ = _git(["rev-parse", "--short", "HEAD"], workspace)
    short_hash = hash_out.strip() if code == 0 else "?"

    return f"提交成功 [{short_hash}] {message}"


# ---------------------------------------------------------------------------
# 注册 LLM 可见的工具
# ---------------------------------------------------------------------------

def register_git_tools(registry: ToolRegistry, cfg: AgentConfig) -> None:
    workspace = cfg.workspace
    output_limit = cfg.output_limit

    # ------------------------------------------------------------------
    # git_status
    # ------------------------------------------------------------------
    def git_status() -> str:
        ensure_git_repo(workspace)
        code, out, err = _git(["status", "--short"], workspace)
        if code != 0:
            return f"错误：{err.strip()}"
        out = out.strip()
        if not out:
            return "工作区干净，无未提交改动。"
        return truncate(out, output_limit)

    registry.register(
        name="git_status",
        schema={
            "type": "function",
            "function": {
                "name": "git_status",
                "description": "查看工作区当前未提交的改动列表。",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        func=git_status,
    )

    # ------------------------------------------------------------------
    # git_log
    # ------------------------------------------------------------------
    def git_log(limit: int = 10) -> str:
        ensure_git_repo(workspace)
        code, out, err = _git(
            ["log", f"-{limit}", "--pretty=format:%h  %ad  %s", "--date=short"],
            workspace,
        )
        if code != 0:
            # 空仓库时 git log 会失败，正常返回提示
            return "（暂无提交记录）"
        return truncate(out.strip(), output_limit)

    registry.register(
        name="git_log",
        schema={
            "type": "function",
            "function": {
                "name": "git_log",
                "description": "查看最近的提交历史，每条包含短 hash、日期和提交信息。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "返回多少条记录，默认 10",
                        }
                    },
                },
            },
        },
        func=git_log,
    )

    # ------------------------------------------------------------------
    # git_show
    # ------------------------------------------------------------------
    def git_show(commit: str) -> str:
        ensure_git_repo(workspace)
        code, out, err = _git(["show", "--stat", commit], workspace)
        if code != 0:
            return f"错误：{err.strip() or '找不到该 commit'}"
        return truncate(out.strip(), output_limit)

    registry.register(
        name="git_show",
        schema={
            "type": "function",
            "function": {
                "name": "git_show",
                "description": "查看某个 commit 的详细信息和改动文件列表。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "commit": {
                            "type": "string",
                            "description": "commit 的短 hash 或完整 hash，也支持 HEAD~1",
                        }
                    },
                    "required": ["commit"],
                },
            },
        },
        func=git_show,
    )

    # ------------------------------------------------------------------
    # git_restore
    # ------------------------------------------------------------------
    def git_restore(commit: str) -> str:
        """将工作区恢复到指定 commit。会丢弃之后的所有改动。

        注意：这是硬回滚，仅用于修复 Agent 连续失败的场景。
        """
        ensure_git_repo(workspace)

        # 先确认 commit 存在
        code, _, _ = _git(["cat-file", "-e", commit], workspace)
        if code != 0:
            return f"错误：找不到 commit {commit}"

        # 记录当前 HEAD，方便告知回滚信息
        _, before, _ = _git(["rev-parse", "--short", "HEAD"], workspace)
        before = before.strip()

        code, out, err = _git(["reset", "--hard", commit], workspace)
        if code != 0:
            return f"回滚失败：{(err or out).strip()}"

        _, after, _ = _git(["rev-parse", "--short", "HEAD"], workspace)
        after = after.strip()

        return f"已回滚：{before} → {after}"

    registry.register(
        name="git_restore",
        schema={
            "type": "function",
            "function": {
                "name": "git_restore",
                "description": (
                    "将工作区恢复到指定 commit 的状态。"
                    "注意：会永久丢弃该 commit 之后的所有改动，请谨慎使用。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "commit": {
                            "type": "string",
                            "description": "目标 commit 的 hash，如 'abc1234' 或 'HEAD~1'",
                        }
                    },
                    "required": ["commit"],
                },
            },
        },
        func=git_restore,
    )
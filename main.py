"""Mini Godot Agent 命令行入口。

用法：
    uv run python main.py "创建一个 Godot 2D 项目"
    uv run python main.py --provider ollama "列出工作区文件"
    uv run python main.py --dry-run "随便一个任务"
    uv run python main.py --list-providers
"""

from __future__ import annotations

import argparse
import sys

from config import PROVIDERS, load_config
from agent.llm import LLMClient
from agent.logger import Logger
from agent.loop import AgentLoop
from agent.memory import Memory
from tools.registry import ToolRegistry
from tools.fs_tools import register_fs_tools


# ---------------------------------------------------------------------------
# 参数解析
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mini-godot-agent",
        description="一个用自然语言操作 Godot 项目的简易 Agent。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  uv run python main.py \"在工作区创建一个 hello.txt\"\n"
            "  uv run python main.py -p ollama \"列出工作区所有文件\"\n"
            "  uv run python main.py --list-providers\n"
        ),
    )
    parser.add_argument(
        "goal",
        nargs="*",
        help="任务描述。多个词会被拼接成一句话。",
    )
    parser.add_argument(
        "-p", "--provider",
        choices=list(PROVIDERS.keys()),
        default=None,
        help="LLM 提供商，不填则从环境变量或默认读取。",
    )
    parser.add_argument(
        "-w", "--workspace",
        default=None,
        help="工作区路径，默认 ./workspace。",
    )
    parser.add_argument(
        "-s", "--max-steps",
        type=int,
        default=None,
        help="Agent 最大步数，默认 12。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印配置，不调用 LLM。",
    )
    parser.add_argument(
        "--list-providers",
        action="store_true",
        help="列出所有已注册的 provider 后退出。",
    )
    return parser


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def list_providers() -> None:
    print("已注册的 provider：\n")
    for name, cfg in PROVIDERS.items():
        key_env = cfg.api_key_env or "（无需 API Key）"
        print(f"  {name:<10} model={cfg.model}")
        print(f"             base_url={cfg.base_url}")
        print(f"             key_env={key_env}")
        print()


def build_agent(cfg, logger: Logger) -> AgentLoop:
    """组装所有模块。"""
    llm = LLMClient(cfg)
    registry = ToolRegistry(cfg)
    register_fs_tools(registry, cfg)
    memory = Memory()
    return AgentLoop(llm, registry, memory, logger, cfg)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # 特殊命令：列出 provider
    if args.list_providers:
        list_providers()
        return 0

    # 校验 goal
    goal = " ".join(args.goal).strip()
    if not goal:
        parser.print_help()
        print("\n错误：请提供任务描述。", file=sys.stderr)
        return 2

    # 组装配置
    try:
        cfg = load_config(
            provider=args.provider,
            workspace=args.workspace,
            max_steps=args.max_steps,
            dry_run=args.dry_run,
        )
    except (ValueError, EnvironmentError) as e:
        print(f"配置错误：{e}", file=sys.stderr)
        return 2

    # dry-run：只打印配置
    if cfg.dry_run:
        print("=== Dry Run ===")
        print(f"provider  : {cfg.provider}")
        print(f"model     : {cfg.provider_config.model}")
        print(f"base_url  : {cfg.provider_config.base_url}")
        print(f"workspace : {cfg.workspace}")
        print(f"max_steps : {cfg.max_steps}")
        print(f"goal      : {goal}")
        return 0

    # 提前校验 API key，避免初始化 Logger 后再报错
    try:
        cfg.provider_config.resolve_api_key()
    except EnvironmentError as e:
        print(f"API Key 缺失：{e}", file=sys.stderr)
        return 2

    # 启动 Agent
    logger = Logger(cfg)
    try:
        loop = build_agent(cfg, logger)
        result = loop.run(goal)

        print()
        print("=" * 60)
        print("最终结果：")
        print("=" * 60)
        print(result)
        print()
        print(f"完整日志：{logger.log_file}")
        return 0

    except KeyboardInterrupt:
        print("\n", file=sys.stderr)
        logger.error("用户中断（Ctrl+C）")
        return 130

    except Exception as e:  # noqa: BLE001
        logger.error(f"未捕获异常：{type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        logger.close()


if __name__ == "__main__":
    sys.exit(main())
"""配置层：定义 provider 与 agent 运行时配置。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Provider 配置
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProviderConfig:
    """单个 LLM provider 的连接信息。"""

    name: str
    base_url: str
    model: str
    api_key_env: str | None  # None 表示不需要 API key（如 Ollama）
    api_key_default: str = ""  # 无 key 时使用的占位值

    def resolve_api_key(self) -> str:
        """从环境变量读取 API key，读不到则返回占位值。"""
        if self.api_key_env is None:
            return self.api_key_default or "not-needed"
        key = os.getenv(self.api_key_env)
        if not key:
            raise EnvironmentError(
                f"缺少环境变量 {self.api_key_env}（provider={self.name}）"
            )
        return key


# 已支持的 provider 注册表。新增模型只改这里。
PROVIDERS: dict[str, ProviderConfig] = {
    "deepseek": ProviderConfig(
        name="deepseek",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-flash",
        api_key_env="DEEPSEEK_API_KEY",
    ),
    "qwen": ProviderConfig(
        name="qwen",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen3-coder-plus",
        api_key_env="DASHSCOPE_API_KEY",
    ),
    "ollama": ProviderConfig(
        name="ollama",
        base_url="http://localhost:11434/v1",
        model="qwen3:8b",
        api_key_env=None,
        api_key_default="ollama",
    ),
}

DEFAULT_PROVIDER = "deepseek"


# ---------------------------------------------------------------------------
# Agent 运行时配置
# ---------------------------------------------------------------------------

@dataclass
class AgentConfig:
    """Agent 主循环的运行参数。"""

    provider: str = DEFAULT_PROVIDER
    workspace: Path = field(default_factory=lambda: Path("./workspace"))
    max_steps: int = 12
    tool_timeout: int = 60
    output_limit: int = 8000
    dry_run: bool = False

    def __post_init__(self) -> None:
        # 统一转成绝对路径，后续 safety 检查依赖这一点
        self.workspace = Path(self.workspace).resolve()
        if self.max_steps <= 0:
            raise ValueError("max_steps 必须为正整数")
        if self.tool_timeout <= 0:
            raise ValueError("tool_timeout 必须为正整数")
        if self.output_limit <= 0:
            raise ValueError("output_limit 必须为正整数")

    @property
    def provider_config(self) -> ProviderConfig:
        if self.provider not in PROVIDERS:
            available = ", ".join(PROVIDERS.keys())
            raise ValueError(
                f"未知 provider: {self.provider}，可选：{available}"
            )
        return PROVIDERS[self.provider]

    @property
    def log_dir(self) -> Path:
        return self.workspace / ".agent" / "logs"

    @property
    def memory_file(self) -> Path:
        return self.workspace / ".agent" / "memory.json"


# ---------------------------------------------------------------------------
# 加载函数
# ---------------------------------------------------------------------------

def load_config(
    provider: str | None = None,
    workspace: str | None = None,
    max_steps: int | None = None,
    dry_run: bool = False,
) -> AgentConfig:
    """从参数 + 环境变量组装 AgentConfig。

    优先级：显式参数 > 环境变量 > 默认值。
    """
    return AgentConfig(
        provider=provider or os.getenv("MINI_AGENT_PROVIDER", DEFAULT_PROVIDER),
        workspace=Path(workspace or os.getenv("MINI_AGENT_WORKSPACE", "./workspace")),
        max_steps=max_steps or int(os.getenv("MINI_AGENT_MAX_STEPS", "12")),
        dry_run=dry_run,
    )


# ---------------------------------------------------------------------------
# 自测：python -m mini_godot_agent.config
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cfg = load_config()
    print(f"provider  : {cfg.provider}")
    print(f"model     : {cfg.provider_config.model}")
    print(f"base_url  : {cfg.provider_config.base_url}")
    print(f"workspace : {cfg.workspace}")
    print(f"max_steps : {cfg.max_steps}")
    print(f"log_dir   : {cfg.log_dir}")

    # 简单校验：如果配置的 provider 需要 key，这里会抛出清晰错误
    try:
        key = cfg.provider_config.resolve_api_key()
        print(f"api_key   : {key[:6]}***")
    except EnvironmentError as e:
        print(f"api_key   : [未配置] {e}")
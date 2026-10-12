# Mini Godot Agent 设计文档 v0.1

## 1. 架构总览

```text
CLI (__main__.py)
  │
  ├── Config (config.py)          读取 provider / model / workspace
  │
  └── AgentLoop (agent/loop.py)
        │
        ├── LLMClient (agent/llm.py)     统一多 provider 接口
        │     ├── DeepSeekProvider
        │     ├── QwenProvider
        │     └── OllamaProvider
        │
        ├── ToolRegistry (tools/registry.py)   注册 + 分发工具
        │     ├── fs_tools     list_files / read_file / write_file / make_dir
        │     └── godot_tools  godot_version / godot_check / godot_run_scene
        │
        ├── Memory (agent/memory.py)     会话内消息历史 + TODO
        │
        ├── Safety (agent/safety.py)     路径沙箱 / 超时 / 截断
        │
        └── Logger (agent/logger.py)     终端 + 文件日志
```

模块职责一句话：

| 模块                   | 职责                                        | 不负责        |
| ---------------------- | ------------------------------------------- | ------------- |
| `__main__.py`          | 解析 CLI 参数，组装依赖，启动 AgentLoop     | 不写业务逻辑  |
| `config.py`            | provider 配置、模型路由、环境变量           | 不发起请求    |
| `agent/loop.py`        | Plan-Act-Observe 主循环                     | 不直接调 HTTP |
| `agent/llm.py`         | 屏蔽不同 provider 差异，统一返回 tool_calls | 不执行工具    |
| `tools/registry.py`    | 工具注册、schema 生成、调用分发             | 不调用 LLM    |
| `tools/fs_tools.py`    | 文件读写，内建沙箱                          | 不碰 Godot    |
| `tools/godot_tools.py` | 封装 Godot headless 命令                    | 不写业务文件  |
| `agent/safety.py`      | 路径检查、超时、输出截断                    | 不管业务      |
| `agent/logger.py`      | 结构化日志                                  | 不做决策      |

## 2. 模块设计

### 2.1 config.py

```python
from dataclasses import dataclass

@dataclass
class ProviderConfig:
    name: str
    base_url: str
    model: str
    api_key_env: str | None

PROVIDERS: dict[str, ProviderConfig] = {
    "deepseek": ProviderConfig(
        name="deepseek",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
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
    ),
}

@dataclass
class AgentConfig:
    provider: str = "deepseek"
    workspace: str = "./workspace"
    max_steps: int = 12
    tool_timeout: int = 60
    output_limit: int = 8000
    dry_run: bool = False
```

设计要点：

- provider 配置集中管理，新增模型只改这里
- Ollama 的 `api_key_env=None`，客户端要用占位 key（如 `"ollama"`）以兼容 OpenAI SDK

### 2.2 agent/llm.py

```python
class LLMClient:
    def __init__(self, cfg: ProviderConfig, tool_schemas: list[dict]):
        ...
    def chat(self, messages: list[dict]) -> ChatResponse:
        """返回统一结构：content + tool_calls"""
```

统一返回结构：

```python
@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict

@dataclass
class ChatResponse:
    content: str | None
    tool_calls: list[ToolCall]
    raw: dict          # 原始响应，用于日志
    usage: dict        # token 统计
```

设计要点：

- **所有 provider 走 OpenAI SDK**，因为 DeepSeek / Qwen / Ollama 都兼容 OpenAI 协议
- 差异化处理放在 `_normalize_response()`：
  - DeepSeek 的 `function.arguments` 是 JSON 字符串，需要 `json.loads`
  - Ollama 有时把 arguments 直接返回 dict，需要判断类型
  - Qwen 的 `tool_calls` 字段名可能与 OpenAI 一致，但要处理 `finish_reason`

### 2.3 tools/registry.py

```python
class ToolRegistry:
    def __init__(self, cfg: AgentConfig):
        self._tools: dict[str, Callable] = {}
        self._schemas: list[dict] = []

    def register(self, name: str, schema: dict, func: Callable): ...
    def schemas(self) -> list[dict]: ...
    def call(self, name: str, arguments: dict) -> str: ...
```

设计要点：

- 工具用装饰器注册更优雅：

```python
@registry.tool(
    name="write_file",
    description="写入文本文件到工作区",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    },
)
def write_file(path: str, content: str) -> str: ...
```

- `call()` 负责 try/except，把异常转成字符串返回给 LLM，而不是让程序崩溃
- 返回值统一为字符串，超过 `output_limit` 截断

### 2.4 tools/fs_tools.py

```python
def list_files(path: str = ".") -> str
def read_file(path: str) -> str
def write_file(path: str, content: str) -> str
def make_dir(path: str) -> str
```

所有路径经过 `safety.resolve_path(workspace, path)`：

```python
def resolve_path(workspace: str, path: str) -> str:
    full = os.path.abspath(os.path.join(workspace, path))
    if not full.startswith(os.path.abspath(workspace)):
        raise SafetyError("路径越界")
    return full
```

### 2.5 tools/godot_tools.py

```python
def godot_version() -> str
def godot_check(project_path: str) -> str
def godot_run_scene(project_path: str, scene: str, seconds: int = 10) -> str
```

统一封装：

```python
def _run_godot(args: list[str], timeout: int) -> str:
    result = subprocess.run(
        ["godot", *args],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return format_result(result.returncode, result.stdout, result.stderr)
```

`godot_check` 对应命令：

```bash
godot --headless --path <project_path> --quit
```

`godot_run_scene` 用 Python timeout 控制运行时长，不用 `--quit-after`：

```bash
timeout 10 godot --headless --path <project_path> res://<scene>
```

设计要点：

- 命令用 list 传参，避免 shell 注入
- 退出码、stdout、stderr 一起返回，LLM 才能判断错误
- Godot 可执行文件路径支持环境变量 `GODOT_BIN` 覆盖

### 2.6 agent/loop.py

```python
class AgentLoop:
    def __init__(self, llm: LLMClient, registry: ToolRegistry,
                 memory: Memory, logger: Logger, cfg: AgentConfig):
        ...

    def run(self, goal: str) -> str:
        self.memory.add_user(goal)
        for step in range(self.cfg.max_steps):
            resp = self.llm.chat(self.memory.messages)
            if not resp.tool_calls:
                self.memory.add_assistant(resp.content)
                return resp.content
            self.memory.add_assistant(resp.content, resp.tool_calls)
            for call in resp.tool_calls:
                result = self.registry.call(call.name, call.arguments)
                self.memory.add_tool_result(call.id, result)
                self.logger.tool(call.name, call.arguments, result)
        return "达到最大步数，未完成。"
```

设计要点：

- 循环只做编排，不做具体执行
- 每步都写入 memory，保持上下文一致
- 达到 max_steps 时优雅退出，不抛异常

### 2.7 agent/memory.py

```python
class Memory:
    def __init__(self):
        self.messages: list[dict] = []
        self.todos: list[str] = []
        self.files_touched: set[str] = set()

    def add_system(self, content: str): ...
    def add_user(self, content: str): ...
    def add_assistant(self, content, tool_calls=None): ...
    def add_tool_result(self, tool_call_id: str, content: str): ...
    def summarize_if_too_long(self, limit: int): ...
```

设计要点：

- MVP 只做会话内记忆
- `summarize_if_too_long` 先占位，等上下文真的爆了再实现
- `files_touched` 用于最后输出摘要

### 2.8 agent/safety.py

```python
class SafetyError(Exception): ...

def resolve_path(workspace: str, path: str) -> str: ...
def truncate(text: str, limit: int) -> str: ...
def run_with_timeout(cmd: list[str], cwd: str, timeout: int): ...
```

### 2.9 agent/logger.py

```python
class Logger:
    def step(self, n: int, msg: str): ...
    def tool(self, name: str, args: dict, result: str): ...
    def error(self, msg: str): ...
```

日志同时输出到终端和 `workspace/.agent/logs/run-*.log`。

## 3. 关键数据流

一次完整任务的时序：

```text
CLI 解析参数
  → 加载 config
  → 构造 LLMClient（注入 tool schemas）
  → 构造 ToolRegistry（注册 fs / godot 工具）
  → 构造 Memory + Logger
  → AgentLoop.run(goal)

AgentLoop:
  memory.add_user(goal)
  loop:
    resp = llm.chat(memory.messages)
    if no tool_calls:
        return content
    memory.add_assistant(tool_calls)
    for call in tool_calls:
        result = registry.call(call.name, call.arguments)
        memory.add_tool_result(call.id, result)
        logger.tool(...)
```

## 4. 接口契约

### 4.1 工具 schema 格式

遵循 OpenAI Function Calling：

```json
{
  "type": "function",
  "function": {
    "name": "godot_check",
    "description": "运行 Godot headless 检查项目是否报错",
    "parameters": {
      "type": "object",
      "properties": {
        "project_path": {"type": "string", "description": "相对 workspace 的项目路径"}
      },
      "required": ["project_path"]
    }
  }
}
```

### 4.2 工具返回值格式

统一为字符串，推荐结构化：

```text
exit_code=0
stdout:
...
stderr:
...
```

或：

```text
写入 workspace/demo/project.godot 成功（共 1234 字节）
```

LLM 需要能从中读出关键信息。

### 4.3 日志格式

```text
[2026-10-10 12:00:01] [STEP 1] 调用 write_file
  args: {"path": "demo/project.godot", "content": "..."}
  result: 写入成功
```

## 5. 关键决策记录

| 决策          | 选择              | 替代方案       | 理由                             |
| ------------- | ----------------- | -------------- | -------------------------------- |
| Provider 抽象 | 统一走 OpenAI SDK | 每家单独 SDK   | 三家都兼容 OpenAI 协议，代码最少 |
| 工具调用      | Function Calling  | ReAct 文本解析 | 结构化，错误率低                 |
| 通用 shell    | 不提供            | 提供 `run_cmd` | 安全，MVP 只封装 Godot           |
| 路径沙箱      | 前缀检查          | 每次询问用户   | 安全优先                         |
| headless 时长 | Python timeout    | `--quit-after` | 跨版本更稳                       |
| 记忆持久化    | 暂不做            | 立即做 JSON    | MVP 先跑通闭环                   |
| 截图验证      | 暂不做            | xvfb + 截图    | 复杂度高，非 P0                  |

## 6. 错误处理策略

| 场景              | 处理                                             |
| ----------------- | ------------------------------------------------ |
| LLM 返回无效 JSON | 捕获异常，把错误信息作为 tool result 返回给 LLM  |
| 工具抛异常        | registry 捕获，返回 `"工具执行失败: ..."` 字符串 |
| Godot 命令超时    | subprocess 捕获 TimeoutExpired，返回 `"超时"`    |
| 路径越界          | 抛 SafetyError，registry 转为字符串返回          |
| LLM API 报错      | 重试 1 次，仍失败则终止并输出原因                |
| 达到 max_steps    | 返回未完成摘要，不抛异常                         |

原则：**工具层错误不杀死 Agent，转化为 LLM 可读的观察结果。**

## 7. 测试策略

| 层级     | 测试对象                   | 方式                          |
| -------- | -------------------------- | ----------------------------- |
| 单元测试 | `resolve_path`、`truncate` | pytest，纯函数                |
| 单元测试 | `fs_tools`                 | 临时目录，读写断言            |
| 单元测试 | `godot_tools`              | mock subprocess               |
| 集成测试 | `LLMClient`                | 真实调用一次，只测格式        |
| 集成测试 | `AgentLoop`                | mock LLM，返回固定 tool_calls |
| 端到端   | 完整任务                   | 真实 Godot + 真实 LLM，手动跑 |

MVP 至少覆盖：`resolve_path`、`fs_tools`、`AgentLoop`（mock LLM）。

## 8. 待办与后续

- M6：bge-m3 接入记忆检索
- M7：Godot MCP 接入
- 后续：截图验证、多 Agent、Git 自动提交

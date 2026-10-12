# Mini Godot Agent 需求文档 v0.1

> 项目代号：MiniGodotAgent  
> 目标：用 Python 写一个简易游戏制作 Agent，能通过自然语言操作 Godot 项目，边写边学 Agent 原理与 Godot 工作流。  
> 默认假设：Python 3.11+，Godot 4.x，命令行运行，OpenAI 兼容 API。

## 1. 背景与目标

我们想做一个“简易游戏制作 Agent”，不是完整商业产品，而是一个可理解、可修改、可扩展的学习项目。

核心目标：

1. 理解 Agent 的基本闭环：规划 → 调用工具 → 观察结果 → 反思 → 继续。
2. 理解 LLM 的 Function Calling / Tool Use。
3. 理解如何把 Godot 接入 Agent：创建文件、运行 headless 命令、读取错误。
4. 最终能完成一个最小可玩原型：一个 Godot 2D 场景，一个可左右移动的角色，能通过 headless 命令验证无报错。

非目标：

- 不做完整 IDE。
- 不直接操控 Godot 编辑器 GUI。
- 不训练模型。
- 不追求“一句话生成完整游戏”。
- 不默认执行危险命令。

## 2. 用户故事

作为学习者/独立开发者，我希望：

1. 输入：“创建一个 Godot 2D 项目，包含 Player 场景，角色能左右移动。”
2. Agent 能规划步骤，并创建 `project.godot`、`main.tscn`、`player.gd` 等文件。
3. Agent 能运行 Godot headless 命令检查项目是否报错。
4. 如果报错，Agent 能读取错误日志并尝试修复。
5. 我能在终端看到每一步：它想做什么、调用了什么工具、结果如何。
6. 所有文件都限制在 `workspace/` 内，避免误伤其他目录。

## 3. 核心流程

```text
用户输入目标
  ↓
Agent 输出计划 / TODO
  ↓
LLM 决定调用哪个工具
  ↓
工具执行：读文件 / 写文件 / 运行 Godot 命令
  ↓
工具结果返回给 LLM
  ↓
LLM 判断：完成？继续？修复？
  ↓
达到完成条件或最大步数后停止
```

关键原则：

- 模型不能只说“完成了”，必须有工具验证。
- 每次修改后尽量运行 Godot 检查。
- 工具结果要截断，避免上下文爆炸。
- 所有操作可回滚，建议 Git。

## 4. 功能需求

### FR-1 工作区管理 P0

- 固定工作区：`./workspace/`。
- 所有文件读写必须限制在工作区内。
- 禁止路径穿越，例如 `../../etc/passwd`。
- 支持列出工作区文件、创建目录、读取文本、写入文本。
- MVP 不提供删除文件工具，避免误删。

验收：

- 传入 `../test.txt` 时拒绝执行。
- 能在 `workspace/demo/` 下创建 Godot 项目文件。

### FR-2 LLM 工具调用 P0

- 使用 OpenAI 兼容的 Function Calling。
- 支持多轮工具调用。
- 每次最多执行 N 步，默认 12 步。
- 支持从环境变量读取 API Key、Base URL、模型名。

验收：

- LLM 能返回工具调用请求。
- Python 能解析 `tool_calls`，执行对应函数，并把结果塞回对话。

### FR-3 文件工具 P0

提供工具：

| 工具                        | 说明           |
| --------------------------- | -------------- |
| `list_files(path)`          | 列出工作区文件 |
| `read_file(path)`           | 读取文本文件   |
| `write_file(path, content)` | 写入文本文件   |
| `make_dir(path)`            | 创建目录       |

验收：

- 能创建 `project.godot`、`.tscn`、`.gd` 文件。
- 写入后能用 `read_file` 读回。

### FR-4 Godot 命令工具 P0

提供工具：

| 工具                                            | 说明                                       |
| ----------------------------------------------- | ------------------------------------------ |
| `godot_check(project_path)`                     | 运行 Godot headless，检查项目导入/脚本错误 |
| `godot_run_scene(project_path, scene, seconds)` | headless 运行指定场景若干秒                |
| `godot_version()`                               | 查看 Godot 版本                            |

参考命令，具体参数按 Godot 4.x 调整：

```bash
godot --headless --path workspace/demo --quit
godot --headless --path workspace/demo res://main.tscn --quit-after 60
```

验收：

- 能捕获 stdout / stderr。
- 命令超时能终止。
- 输出过长时截断。
- 返回结果包含退出码。

### FR-5 Agent 循环 P0

- 接收用户目标。
- 维护消息历史。
- 循环调用 LLM。
- 如果 LLM 要调用工具，就执行工具并继续。
- 如果 LLM 不再调用工具，就输出最终回答。
- 达到最大步数时停止，并报告未完成。

验收：

- 输入一个简单 Godot 任务，Agent 能自动完成至少一次“写文件 → 运行检查 → 根据结果继续”。

### FR-6 记忆与状态 P1

MVP 先做会话内记忆：

- 当前消息历史。
- 当前 TODO 列表。
- 已创建/修改的文件列表。
- 最近一次 Godot 命令结果。

后续可持久化到：

```text
workspace/.agent/memory.json
```

### FR-7 日志与可观测 P0

终端输出每一步：

```text
[STEP 1] LLM 决定调用 write_file
[TOOL] write_file(path=project.godot)
[RESULT] 写入成功
[STEP 2] LLM 决定调用 godot_check
[TOOL] godot_check(project_path=demo)
[RESULT] exit_code=0
```

同时写入日志文件：

```text
workspace/.agent/logs/run-YYYYMMDD-HHMMSS.log
```

### FR-8 安全与确认 P0

- 命令工具不直接执行任意 shell，MVP 只封装 Godot 命令。
- 如果未来加入通用 `run_cmd`，必须有白名单和人工确认。
- 禁止删除、移动、覆盖工作区外文件。
- 超时默认 60 秒。
- 工具输出默认截断到 8000 字符。

### FR-9 验证与完成条件 P0

一个任务算完成，至少满足：

1. 目标文件已生成。
2. Godot headless 检查退出码为 0。
3. 如果运行场景，没有脚本解析错误。
4. Agent 输出修改摘要和验证结果。

### FR-10 CLI P0

基础命令：

```bash
python -m mini_godot_agent "创建一个 Godot 2D 项目，角色能左右移动"
```

可选参数：

```bash
--workspace ./workspace
--max-steps 12
--model gpt-4o-mini
--dry-run
```

## 5. 非功能需求

- 可学习：模块清晰，每个文件不超过 200 行优先。
- 可测试：工具函数尽量纯函数，可用 pytest。
- 可扩展：后续能接 MCP、Godot MCP、Unity MCP。
- 成本可控：限制步数、截断输出、记录 token 用量。
- 安全：路径沙箱、命令白名单、超时。
- 跨平台：优先支持 macOS / Linux，Windows 尽量兼容。

## 6. 系统架构草图

```text
CLI
  ↓
Agent Loop
  ↓
LLM Client  ←→  OpenAI 兼容 API
  ↓
Tool Registry
  ↓
┌──────────────┬──────────────┬──────────────┐
│ 文件工具      │ Godot 工具    │ 记忆/日志工具 │
└──────────────┴──────────────┴──────────────┘
  ↓
workspace/  ←  Godot 项目
```

## 7. 建议目录结构

```text
mini_godot_agent/
  __main__.py
  config.py
  agent/
    loop.py
    llm.py
    prompts.py
    memory.py
    safety.py
  tools/
    registry.py
    fs_tools.py
    godot_tools.py
  workspace/
  tests/
    test_fs_tools.py
    test_godot_tools.py
    test_agent_loop.py
  docs/
    requirements.md
    design.md
```

## 8. 里程碑与学习检查点

### M0 需求文档 P0

产出：本文档。  
学习：明确 Agent 边界与验收标准。

### M1 最小 LLM 工具调用 P0

产出：能调用 `list_files`、`read_file`、`write_file`。  
学习：Function Calling、消息格式、工具结果回填。

### M2 工作区安全 P0

产出：路径沙箱、超时、输出截断。  
学习：Agent 安全边界。

### M3 Godot 工具 P0

产出：`godot_version`、`godot_check`、`godot_run_scene`。  
学习：Godot headless 工作流、退出码、stdout/stderr。

### M4 Agent 循环 P0

产出：多步循环、最大步数、日志。  
学习：Plan-Act-Observe 闭环。

### M5 第一个真实任务 P0

目标：生成最小 Godot 2D 项目，角色左右移动，headless 验证通过。  
学习：从自然语言到可运行项目。

### M6 记忆与 TODO P1

产出：TODO 列表、项目状态、运行日志。  
学习：Agent 状态管理。

### M7 MCP / 截图 / 多 Agent P2

产出：接 Godot MCP、截图验证、Planner/Coder/Tester 分工。  
学习：高级 Agent 架构。

## 9. 验收标准

MVP 完成时，应满足：

1. 运行 CLI，输入自然语言任务。
2. Agent 在 `workspace/demo/` 创建 Godot 项目。
3. 生成 `project.godot`、`main.tscn`、`player.gd`。
4. `godot_check("demo")` 退出码为 0。
5. Agent 输出修改摘要和验证结果。
6. 所有操作限制在 `workspace/`。
7. 每步有终端日志和文件日志。
8. 如果 Godot 报错，Agent 至少尝试读取错误并修复一次。

## 10. ~~风险与开放问题~~  已确认的技术决策

## 模型策略建议

### 主模型推荐：DeepSeek API

**理由**：DeepSeek API 原生支持 OpenAI 兼容的 Function Calling 格式，且支持 `strict` 模式，模型会严格遵循 JSON Schema 输出工具调用参数。这对 Agent 的工具调用可靠性非常重要。DeepSeek 的 Tool Calls 官方文档给出了完整的 Python 示例，可以直接对照实现。

**base_url**: `https://api.deepseek.com`  
**模型名**: `deepseek-chat` 或 `deepseek-flash`

### 备用模型：千问 API

千问同样支持 Function Calling，且提供 OpenAI 兼容的接口。支持的模型系列包括 Qwen3-Max、Qwen3-Plus、Qwen-Coder 等。其中 **Qwen-Coder 系列**特别值得关注，因为它针对代码生成做了优化，适合你后续让 Agent 写 Godot 的 `.gd` 脚本和 `.tscn` 场景文件。

需要注意的是，千问对某些模型（如 GLM 系列）有额外的 `extra_body` 参数要求，但 Qwen 系列本身没有这个限制。

### 本地模型：Ollama qwen3:8b

Ollama 已经原生支持 Tool Calling，且文档中明确以 `qwen3` 作为示例模型。Python SDK 的用法也很直接，`tools` 参数可以直接传入函数或 JSON Schema。

**限制**：qwen3:8b 作为 8B 参数模型，在多步工具调用和复杂规划任务上能力有限。根据一份第三方评测，8B 模型在工具调用准确率测试中约为 75%。建议把 Ollama 作为**离线开发/调试用**，或在简单任务中作为低成本替代。

### Embedding 模型：bge-m3

bge-m3 是纯 Embedding 模型，**不支持 Function Calling**，所以不能直接作为 Agent 的主模型。它的用途应该是：

- **记忆检索**：把项目历史、代码片段、Godot 文档向量化，做语义搜索
- **知识库**：为 Agent 提供 Godot API 参考、常见错误模式的检索
- **RAG**：在 Agent 需要查 Godot 文档时，先用 bge-m3 检索相关段落，再注入上下文

这可以在 **M6（记忆与状态）** 阶段接入，不是 MVP 必需项。

## 推荐的模型路由设计

在 `config.py` 中做一个简单的模型配置层：

```python
MODEL_CONFIGS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "api_key_env": "DEEPSEEK_API_KEY",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3-coder-plus",  # 或 qwen-plus
        "api_key_env": "DASHSCOPE_API_KEY",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "qwen3:8b",
        "api_key_env": None,  # Ollama 不需要 key
    },
}
```

CLI 增加 `--provider` 参数：

```bash
python -m mini_godot_agent "创建 Godot 2D 项目" --provider deepseek
python -m mini_godot_agent "创建 Godot 2D 项目" --provider ollama
```

这样你可以在不同模型之间切换，对比同一个任务在不同模型上的表现。这本身就是很好的学习过程。

## Godot 4.7.1 的 headless 验证

Godot 4.x 的 headless 模式参数从 4.0 开始就稳定了：`--headless` 抑制窗口和音频驱动。但 `--quit-after` 这个参数需要确认具体版本是否支持。

安全做法是：

```bash
# 检查项目导入，不运行场景
godot --headless --path workspace/demo --quit

# 运行场景，用 timeout 控制时长（比依赖 --quit-after 更可靠）
timeout 10 godot --headless --path workspace/demo res://main.tscn
```

用 Python 的 `subprocess` 配合 `timeout=10` 来控制运行时长，比依赖 Godot 内部参数更可控。

## 更新后的开放问题

回到需求文档第 10 节，你的信息已经解决了大部分：

| 问题                   | 结论                                                         |
| ---------------------- | ------------------------------------------------------------ |
| Godot 具体版本         | **4.7.1**，headless 用 `--headless`，运行时长用 Python `timeout` 控制 |
| 模型选择               | **主：DeepSeek**（Function Calling 稳定）；备：千问（Qwen-Coder 适合代码）；本地：Ollama qwen3:8b（离线调试） |
| 是否允许通用 `run_cmd` | 仍建议**不提供**通用 shell，只封装 Godot 命令。MVP 阶段保持安全边界 |
| 是否需要截图验证       | **MVP 不做**。headless 模式无法截图，后续可加 `--rendering-driver` 配合 xvfb 做视觉验证 |
| 是否自动 Git 提交      | **建议做**，每步 Agent 修改后自动 `git add -A && git commit -m "agent: step N"`，方便回滚 |

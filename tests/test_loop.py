from config import AgentConfig
from agent.llm import LLMClient
from agent.logger import Logger
from agent.memory import Memory
from agent.loop import AgentLoop
from tools.registry import ToolRegistry
from tools.fs_tools import register_fs_tools

cfg = AgentConfig(workspace="./workspace", max_steps=8)
logger = Logger(cfg)

try:
    llm = LLMClient(cfg)
    registry = ToolRegistry(cfg)
    register_fs_tools(registry, cfg)
    memory = Memory()
    loop = AgentLoop(llm, registry, memory, logger, cfg)

    result = loop.run("请在工作区根目录创建一个 hello.txt 文件，内容为：Hello, Godot!")
    print("\n" + "=" * 50)
    print("最终结果：")
    print(result)
finally:
    logger.close()
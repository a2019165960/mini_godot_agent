from config import AgentConfig
from tools.registry import ToolRegistry

cfg = AgentConfig()
registry = ToolRegistry(cfg)

# 定义一个假工具用于测试
def fake_echo(text: str) -> str:
    return f"echo: {text}"

schema = {
    "type": "function",
    "function": {
        "name": "fake_echo",
        "description": "测试用回显",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string"}
            },
            "required": ["text"],
        },
    },
}

registry.register("fake_echo", schema, fake_echo)

# 正常调用
print("正常:", registry.call("fake_echo", {"text": "hello"}))

# 参数错误，观察能否优雅捕获
print("参数错:", registry.call("fake_echo", {"wrong": "hello"}))

# 不存在的工具
print("不存在:", registry.call("nonexistent", {}))

# 长输出截断
long_text = "a" * 10000
print("截断长度:", len(registry._truncate(long_text)))
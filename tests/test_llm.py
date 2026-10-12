from config import load_config
from agent.llm import LLMClient

cfg = load_config(provider="deepseek")
client = LLMClient(cfg)

messages = [
    {"role": "system", "content": "你是一个游戏制作助手。"},
    {"role": "user", "content": "你好，请介绍一下你自己。"}
]

resp = client.chat(messages)
print("content:", resp.content)
print("usage:", resp.usage)
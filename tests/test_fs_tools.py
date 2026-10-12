from config import AgentConfig
from tools.registry import ToolRegistry
from tools.fs_tools import register_fs_tools

cfg = AgentConfig(workspace="./workspace")
registry = ToolRegistry(cfg)
register_fs_tools(registry, cfg)

# 1. 写文件
print(registry.call("write_file", {"path": "demo/test.txt", "content": "hello world"}))

# 2. 读文件
print(registry.call("read_file", {"path": "demo/test.txt"}))

# 3. 列目录
print(registry.call("list_files", {"path": "demo"}))

# 4. 路径越界（重点测试）
print(registry.call("read_file", {"path": "../../config.py"}))

# 5. 读不存在的文件
print(registry.call("read_file", {"path": "demo/nonexistent.txt"}))
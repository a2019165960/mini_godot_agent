from config import AgentConfig
from agent.logger import Logger

cfg = AgentConfig(workspace="./workspace")
log = Logger(cfg)

log.info("Agent 启动")
log.step(1, "LLM 决定调用 write_file")
log.tool("write_file", {"path": "demo/main.gd", "content": "extends Node"}, "写入成功：demo/main.gd（13 字符）")
log.step(2, "LLM 决定调用 godot_check")
log.tool("godot_check", {"project_path": "demo"}, "exit_code=0\nstdout: ...")
log.error("Godot 未安装，请检查 PATH")
log.info("任务结束")
log.close()

print(f"\n日志已写入：{log.log_file}")
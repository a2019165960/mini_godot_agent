"""日志模块：终端彩色输出 + 文件完整记录。"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from config import AgentConfig


# 终端颜色 ANSI
RESET = "\033[0m"
GREEN = "\033[92m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
RED = "\033[91m"
GRAY = "\033[90m"


class Logger:
    def __init__(self, cfg: AgentConfig):
        self.cfg = cfg
        self.log_dir: Path = cfg.log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.log_file: Path = self.log_dir / f"run-{ts}.log"
        # 打开文件，全程追加写入
        self._fh = self.log_file.open("a", encoding="utf-8")

        self.info(f"日志已开启：{self.log_file}")

    # ------------------------------------------------------------------
    # 对外方法
    # ------------------------------------------------------------------
    def info(self, msg: str) -> None:
        self._write(f"[INFO] {msg}", color=GRAY)

    def step(self, n: int, msg: str) -> None:
        self._write(f"[STEP {n}] {msg}", color=BLUE, bold_prefix=True)

    def tool(self, name: str, args: dict[str, Any], result: str) -> None:
        """记录一次工具调用。终端截断，文件完整。"""
        args_str = json.dumps(args, ensure_ascii=False, indent=2)
        self._write(
            f"[TOOL] {name}\n  args: {args_str}\n  result: {result}",
            color=GREEN,
        )

    def error(self, msg: str) -> None:
        self._write(f"[ERROR] {msg}", color=RED)

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------
    def _write(self, text: str, color: str = "", bold_prefix: bool = False) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        time_prefix = f"{GRAY}[{ts}]{RESET} "

        # 终端输出（带颜色）
        if bold_prefix:
            # 把第一行的标签加粗，方便阅读
            first_line, _, rest = text.partition("\n")
            colored = f"{color}{first_line}{RESET}"
            if rest:
                colored += f"\n{rest}"
        else:
            colored = f"{color}{text}{RESET}"

        terminal_text = f"{time_prefix}{colored}"
        print(terminal_text, flush=True)

        # 文件输出（无颜色、带完整时间戳）
        full_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        file_text = f"[{full_ts}] {text}\n"
        self._fh.write(file_text)
        self._fh.flush()
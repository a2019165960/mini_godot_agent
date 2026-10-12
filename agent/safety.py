"""安全边界：限制所有文件操作必须在 workspace 内。"""

from __future__ import annotations
from pathlib import Path


class SafetyError(Exception):
    """安全违规异常。"""
    pass


def resolve_path(workspace: Path, path: str) -> Path:
    """将相对路径解析为绝对路径，并验证其位于 workspace 内。

    Raises:
        SafetyError: 如果路径越界或非法。
    """
    base = workspace.resolve()
    # 支持绝对路径输入，但最终必须归入 base 下
    target = (base / path).resolve()

    if not target.is_relative_to(base):
        raise SafetyError(f"路径越界，拒绝访问: {path}")

    return target


def truncate(text: str, limit: int) -> str:
    """截断过长文本，并标注截断信息。"""
    if len(text) <= limit:
        return text
    remain = len(text) - limit
    return text[:limit] + f"\n...[输出过长，已截断 {remain} 字符]"
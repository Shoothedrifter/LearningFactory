"""
tools/filesystem.py
本地文件系统工具：写文件和创建目录。

供主 Agent 在 Skill 输出阶段使用，用于生成本地学习路径文件。
"""

import os
from pathlib import Path

# 写文件时的最大内容长度（防止意外写入超大文件）
_MAX_CONTENT_CHARS = 100_000


async def write_file(path: str, content: str) -> str:
    """
    将内容写入本地文件。如果父目录不存在，会自动创建。

    参数:
        path:    相对于当前工作目录的文件路径（如 "learning-pytorch/README.md"）
        content: 要写入的文件内容

    返回:
        操作结果描述（成功路径 + 字符数，或错误信息）
    """
    try:
        # 安全检查：防止路径穿越到项目外
        target = Path(path).resolve()
        cwd = Path.cwd().resolve()
        try:
            target.relative_to(cwd)
        except ValueError:
            return f"[错误] 拒绝写入：路径 '{path}' 位于当前工作目录之外"

        # 内容长度检查
        if len(content) > _MAX_CONTENT_CHARS:
            return f"[错误] 内容过长（{len(content)} 字符，上限 {_MAX_CONTENT_CHARS}）"

        # 自动创建父目录
        target.parent.mkdir(parents=True, exist_ok=True)

        # 写入文件（UTF-8 编码）
        target.write_text(content, encoding="utf-8")

        # 返回相对于 cwd 的路径，便于阅读
        rel_path = target.relative_to(cwd)
        return f"[成功] 已写入 {rel_path}（{len(content)} 字符）"

    except Exception as e:
        return f"[错误] 写入失败: {e}"


async def list_directory(path: str = ".") -> str:
    """
    列出指定目录下的文件和子目录。

    参数:
        path: 要列出的目录路径（默认当前目录）

    返回:
        目录内容列表
    """
    try:
        target = Path(path).resolve()
        if not target.exists():
            return f"[错误] 目录不存在: {path}"
        if not target.is_dir():
            return f"[错误] 不是目录: {path}"

        entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name))
        lines = []
        for entry in entries:
            prefix = "[DIR]  " if entry.is_dir() else "[FILE] "
            lines.append(f"{prefix}{entry.name}")

        return f"目录 {path} 内容（共 {len(lines)} 项）:\n" + "\n".join(lines)

    except Exception as e:
        return f"[错误] 列出目录失败: {e}"


# ── Tool Schema ────────────────────────────────────────────────────────────────

FILESYSTEM_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "将内容写入本地文件。自动创建所需的父目录。"
                "用于生成学习路径、资源列表等输出文件。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "目标文件路径，如 'learning-pytorch/README.md'",
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的文件内容（支持 Markdown 格式）",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "列出指定目录下的文件和子目录，用于确认文件是否已正确创建。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要列出的目录路径（默认当前目录 '.'）",
                    },
                },
                "required": [],
            },
        },
    },
]

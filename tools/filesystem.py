"""
tools/filesystem.py
本地文件系统工具：写文件和创建目录。

供主 Agent 在 Skill 输出阶段使用，用于生成本地学习路径文件。
"""

import os
from pathlib import Path

# 单次写入/追加的分块策略上限：超长 content 会让模型生成的 JSON 参数
# 截断/转义失败（概率性故障），这里是确定性边界——超限直接拒绝并引导分块。
# 数值与全链路文案一致（SKILL.md / schema / enforcement / 错误引导均为 1500）。
_MAX_CHUNK_CHARS = 1_500


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

        # 分块硬上限：超限拒绝落盘并引导分块（见模块头 _MAX_CHUNK_CHARS 注释）
        if len(content) > _MAX_CHUNK_CHARS:
            return (
                f"[错误] 单次写入内容过长（{len(content)} 字符，分块上限 {_MAX_CHUNK_CHARS}）。"
                "请只保留文件开头（≤1500 字符），剩余内容用 append_file 逐块追加"
                "（每块 ≤1500 字符）；不同文件的写入可在同一轮并行调用。"
            )

        # 自动创建父目录
        target.parent.mkdir(parents=True, exist_ok=True)

        # 写入文件（UTF-8 编码）
        target.write_text(content, encoding="utf-8")

        # 返回相对于 cwd 的路径，便于阅读
        rel_path = target.relative_to(cwd)
        return f"[成功] 已写入 {rel_path}（{len(content)} 字符）"

    except Exception as e:
        return f"[错误] 写入失败: {e}"


async def append_file(path: str, content: str) -> str:
    """
    将内容追加到本地文件末尾。文件不存在时自动创建（含父目录）。

    专用于长文档分块写入：先 write_file 写首块，再多次 append_file 追加，
    避免单次工具调用的 content 过长导致模型生成的 JSON 参数被截断。

    参数:
        path:    相对于当前工作目录的文件路径
        content: 要追加的文件内容

    返回:
        操作结果描述（成功路径 + 字符数，或错误信息）
    """
    try:
        # 安全检查：防止路径穿越到项目外（与 write_file 一致）
        target = Path(path).resolve()
        cwd = Path.cwd().resolve()
        try:
            target.relative_to(cwd)
        except ValueError:
            return f"[错误] 拒绝写入：路径 '{path}' 位于当前工作目录之外"

        # 分块硬上限（与 write_file 同一上限与文案基调）
        if len(content) > _MAX_CHUNK_CHARS:
            return (
                f"[错误] 单次追加内容过长（{len(content)} 字符，分块上限 {_MAX_CHUNK_CHARS}）。"
                "请把本块拆小（≤1500 字符）再追加；"
                "不同文件的追加可在同一轮并行调用，但同一文件的块必须逐轮顺序追加。"
            )

        # 自动创建父目录
        target.parent.mkdir(parents=True, exist_ok=True)

        # 追加写入（文件不存在时 "a" 模式自动创建）；UTF-8 编码
        with target.open("a", encoding="utf-8") as f:
            f.write(content)

        rel_path = target.relative_to(cwd)
        return f"[成功] 已追加 {len(content)} 字符到 {rel_path}"

    except Exception as e:
        return f"[错误] 追加失败: {e}"


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
                "每次写入不超过 1500 字符（超限会被拒绝）——长文档分块写入："
                "本工具只写文件开头，剩余内容用 append_file 逐块追加。"
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
                        "description": "要写入的文件内容（不超过 1500 字符，超限会被拒绝）",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "append_file",
            "description": (
                "将内容追加到本地文件末尾（文件不存在则创建）。"
                "长文档必须分块写入：先用 write_file 写开头（≤1500 字符），"
                "再用本工具逐块追加剩余内容（每块 ≤1500 字符），"
                "避免单次 content 过长导致参数解析失败。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "目标文件路径（须与此前 write_file 的路径一致）",
                    },
                    "content": {
                        "type": "string",
                        "description": "要追加的内容（不超过 1500 字符，超限会被拒绝）",
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

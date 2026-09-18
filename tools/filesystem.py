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


async def write_file(path: str, content: str, overwrite: bool = False) -> str:
    """
    将内容写入本地文件。如果父目录不存在，会自动创建。

    覆盖防线：目标文件已存在且非空时默认拒绝（防续写场景盲写毁掉已完成内容），
    需整体重写须显式传 overwrite=True。

    参数:
        path:      相对于当前工作目录的文件路径（如 "learning-pytorch/README.md"）
        content:   要写入的文件内容
        overwrite: 目标文件已存在且非空时是否允许覆盖（默认 False 拒绝）

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

        # 覆盖防线：既有非空文件默认拒绝（transformer 日志实害：盲写静默覆盖毁掉完整文档）。
        # 续写请走 append_file；确需整体重写先 read_file 确认既有内容再显式 overwrite=true。
        if target.exists() and target.is_file() and target.stat().st_size > 0 and overwrite is not True:
            existing = target.read_text(encoding="utf-8", errors="replace")
            return (
                f"[错误] 目标文件已存在且非空（{len(existing)} 字符），默认拒绝覆盖。"
                "续写/补充内容请用 append_file；"
                "确实要整体重写请先 read_file 确认既有内容，再传 overwrite=true。"
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

        # 空内容守卫：空追加不产生任何效果、只会白耗一轮工具调用
        # （2026-09-18 实测日志：模型曾发出 content="" 的追加浪费一轮）
        if content == "":
            return (
                "[错误] 拒绝空追加（content 为 0 字符）：空追加不产生任何效果、"
                "只会浪费一轮工具调用。请带上实际要追加的内容（≤1500 字符）再调用。"
            )

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


async def read_file(path: str, offset: int = 0, limit: int = 200) -> str:
    """
    读取本地文本文件内容（按行分页返回）。

    续写/补充既有文件前的必经步骤——先读才知道文件已有什么，
    避免 write_file 盲目覆盖造成内容丢失。

    参数:
        path:   相对于当前工作目录的文件路径
        offset: 起始行号（0 起，默认从文件头开始）
        limit:  最多读取的行数（默认 200 行）

    返回:
        头部元信息（总行数/字符数/当前页范围）+ 文件内容；超出部分尾部提示续读 offset
    """
    try:
        # 安全检查：与写入一致，禁止路径穿越到项目外
        target = Path(path).resolve()
        cwd = Path.cwd().resolve()
        try:
            target.relative_to(cwd)
        except ValueError:
            return f"[错误] 拒绝读取：路径 '{path}' 位于当前工作目录之外"

        if not target.exists():
            return f"[错误] 文件不存在: {path}（可先用 list_directory 查看目录内容）"
        if target.is_dir():
            return f"[错误] 是目录不是文件: {path}（查看目录内容请用 list_directory）"

        text = target.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()

        # 空文件特判（避免头部出现"第 -1 行"）
        if not lines:
            return f"[文件] {target.relative_to(cwd)}（空文件，0 字符）"

        # 参数规整：负值与 0 行上限的防御性钳制
        offset = max(0, offset)
        limit = max(1, limit)

        page = lines[offset : offset + limit]
        if not page:
            return f"[错误] offset={offset} 超出文件总行数（共 {len(lines)} 行）"

        header = (
            f"[文件] {target.relative_to(cwd)}（共 {len(lines)} 行 / {len(text)} 字符，"
            f"显示第 {offset}-{offset + len(page) - 1} 行）\n"
        )
        body = "\n".join(page)
        if offset + limit < len(lines):
            body += f"\n[提示] 还有 {len(lines) - offset - limit} 行未显示，用 offset={offset + limit} 继续读取"
        return header + body

    except Exception as e:
        return f"[错误] 读取失败: {e}"


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
                "多个不同文件的 write_file 可在同一轮并行发起"
                "（多个工具调用放同一条消息），节约轮次。"
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
                    "overwrite": {
                        "type": "boolean",
                        "description": "目标文件已存在且非空时必须显式传 true 才会覆盖（默认 false 拒绝覆盖）",
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
                "不同文件的追加可在同一轮并行发起；"
                "同一文件的多个块必须逐轮顺序追加（每轮一块）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "目标文件路径（分块续写同一文件时保持路径不变）",
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
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "读取本地文本文件内容（默认前 200 行，超出用 offset 续读）。"
                "续写、补充或重写既有文件前必须先 read_file 了解已有内容，"
                "避免盲目覆盖造成内容丢失。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要读取的文件路径",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "起始行号（0 起，默认 0）",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多读取的行数（默认 200）",
                    },
                },
                "required": ["path"],
            },
        },
    },
]

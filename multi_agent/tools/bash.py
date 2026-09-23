"""
tools/bash.py
Bash 工具实现：在子进程中执行 shell 命令。
替代原来 claude_agent_sdk 内置的 Bash 工具，主要供 repo_analyzer 子 Agent 使用。

⚠️  安全提示：此工具会在本机执行任意命令，仅在可信环境中使用。
"""

import asyncio

# 单条命令的最长执行时间（秒）
_TIMEOUT_SECONDS = 30

# 命令输出的最大字符数（stdout + stderr 合计）
_MAX_OUTPUT_CHARS = 5000


async def bash(command: str) -> str:
    """
    异步执行 shell 命令，返回 stdout + stderr 合并后的字符串。
    超时或出错时返回描述性错误信息，不会抛出异常（让模型自行决定如何处理）。
    """
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return f"[错误] 命令执行超时（>{_TIMEOUT_SECONDS}s）: {command}"
    except Exception as e:
        return f"[错误] 无法执行命令: {e}"

    # 合并输出，优先显示 stdout，stderr 附在末尾
    output_parts = []
    if stdout:
        output_parts.append(stdout.decode("utf-8", errors="replace"))
    if stderr:
        output_parts.append(f"[stderr]\n{stderr.decode('utf-8', errors='replace')}")

    combined = "\n".join(output_parts).strip()

    # 截断超长输出
    if len(combined) > _MAX_OUTPUT_CHARS:
        combined = combined[:_MAX_OUTPUT_CHARS] + f"\n[输出已截断，共 {len(combined)} 字符]"

    # 返回退出码 + 输出
    exit_code_info = f"[退出码: {proc.returncode}]"
    return f"{exit_code_info}\n{combined}" if combined else exit_code_info


# ── Tool Schema ────────────────────────────────────────────────────────────────

BASH_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": (
                "在本地执行 shell 命令。可用于克隆代码仓库、查看文件结构、"
                "运行脚本、搜索代码内容等。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 shell 命令，例如 'ls -la' 或 'cat README.md'",
                    }
                },
                "required": ["command"],
            },
        },
    }
]

"""
tools/mcp_client.py
MCP 连接管理器：提供通用的 MCP 工具调用函数。

使用 mcp SDK 的 streamable_http_client 连接 HTTP 类型的 MCP 服务器。
每次工具调用创建独立连接（HTTP 无状态，开销可忽略）。
"""

import os

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def call_mcp_tool(server_url: str, tool_name: str, arguments: dict) -> str:
    """
    调用指定 MCP 服务器上的工具，返回结果文本。

    参数:
        server_url: MCP 服务器的 HTTP 端点 URL，相当于工具的供应商
        tool_name:  要调用的工具名称
        arguments:  工具参数字典

    返回:
        工具返回的文本内容（str）
    """
    api_key = os.environ.get("GLM_API_KEY", "")
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    async with streamablehttp_client(url=server_url, headers=headers) as (
        read_stream,
        write_stream,
        _,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)

    # 从 result.content 中提取所有 TextContent 的文本
    texts = []
    for block in result.content:
        if hasattr(block, "text"):
            texts.append(block.text)
        else:
            texts.append(str(block))

    return "\n".join(texts)

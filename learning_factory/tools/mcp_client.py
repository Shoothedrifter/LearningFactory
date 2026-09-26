"""
tools/mcp_client.py
MCP 连接管理器：提供通用的 MCP 工具调用函数。

使用 mcp SDK 的 streamable_http_client 连接 HTTP 类型的 MCP 服务器。
每次工具调用创建独立连接（HTTP 无状态，开销可忽略）。
"""

import os

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


def _get_mcp_api_key() -> str:
    """
    MCP 工具认证 Key：专用 MCP_API_KEY 优先，缺省回落 LLM_API_KEY。

    产品语义（非旧名兼容）：模型与研究工具默认来自同一供应商，未设
    专用 Key 即共用模型 API 的 Key；仅当供应商对 MCP 单独发 Key 时
    才需要另设 MCP_API_KEY。
    """
    return os.environ.get("MCP_API_KEY") or os.environ.get("LLM_API_KEY", "")


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
    api_key = _get_mcp_api_key()
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

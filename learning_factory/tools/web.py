"""
tools/web.py
WebSearch 和 WebFetch 工具的具体实现。

通过 MCP 服务器实现：
  - web_search → web_search_prime MCP 工具
  - web_fetch  → web_reader MCP 工具
对外接口保持不变（函数签名、tool schema），提示词无需修改。
"""

from .mcp_client import call_mcp_tool
from ..config import get_web_search_url, get_web_reader_url


async def web_search(query: str) -> str:
    """
    使用 MCP web_search_prime 搜索网页，返回格式化的搜索结果字符串。
    """
    return await call_mcp_tool(
        server_url=get_web_search_url(),
        tool_name="web_search_prime",
        arguments={"search_query": query, "location": "cn"},
    )


async def web_fetch(url: str) -> str:
    """
    获取指定 URL 的网页内容，返回 Markdown 格式。
    """
    return await call_mcp_tool(
        server_url=get_web_reader_url(),
        tool_name="webReader",
        arguments={"url": url, "return_format": "markdown"},
    )


# ── Tool Schema（供模型 function calling 使用）────────────────────────────────

# OpenAI 格式的工具定义，默认供应商端点原生兼容此格式
WEB_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "在互联网上搜索信息，返回相关网页的标题、链接和摘要。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，建议简洁精准",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "获取指定 URL 的完整网页内容，适合阅读文档、README 或具体文章。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要访问的完整 URL，必须包含 http:// 或 https://",
                    }
                },
                "required": ["url"],
            },
        },
    },
]

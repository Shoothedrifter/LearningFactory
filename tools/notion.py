"""
tools/notion.py
Notion 工具实现：直接调用 Notion REST API。
替代原来通过 MCP 服务器中转的 mcp__notion__API-post-search
和 mcp__notion__API-patch-block-children。

Notion API 文档: https://developers.notion.com/reference
"""

import json
import os
import httpx

# Notion API 版本（固定，避免接口变动影响）
_NOTION_VERSION = "2022-06-28"
_NOTION_BASE = "https://api.notion.com/v1"

# 搜索结果最多返回条数
_MAX_SEARCH_RESULTS = 5


def _get_headers() -> dict:
    """构造 Notion API 请求头，从环境变量读取 Token。"""
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        raise ValueError("未设置 NOTION_TOKEN 环境变量")
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": _NOTION_VERSION,
        "Content-Type": "application/json",
    }


# ── notion_search ──────────────────────────────────────────────────────────────

async def notion_search(query: str) -> str:
    """
    在 Notion workspace 中搜索页面和数据库。
    对应原来的 mcp__notion__API-post-search。
    返回格式化的搜索结果（ID、标题、类型、URL）。
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{_NOTION_BASE}/search",
            headers=_get_headers(),
            json={
                "query": query,
                "page_size": _MAX_SEARCH_RESULTS,
            },
        )
        resp.raise_for_status()

    results = resp.json().get("results", [])
    if not results:
        return f"在 Notion 中未找到与 '{query}' 相关的内容。"

    lines = [f"Notion 搜索结果（关键词: {query}）:\n"]
    for item in results:
        obj_type = item.get("object", "unknown")  # "page" 或 "database"
        item_id = item.get("id", "")
        url = item.get("url", "")

        # 提取标题（页面和数据库的标题字段结构稍有不同）
        title = _extract_title(item)

        lines.append(f"• [{obj_type.upper()}] {title}")
        lines.append(f"  ID: {item_id}")
        lines.append(f"  URL: {url}\n")

    return "\n".join(lines)


def _extract_title(item: dict) -> str:
    """从 Notion 对象中提取标题文本（兼容 page 和 database）。"""
    try:
        props = item.get("properties", {})
        # 页面通常有 "title" 或 "Name" 属性
        for key in ("title", "Title", "Name", "名称"):
            if key in props:
                title_arr = props[key].get("title", [])
                if title_arr:
                    return "".join(t.get("plain_text", "") for t in title_arr)
        # database 的标题在 title 字段
        title_arr = item.get("title", [])
        if title_arr:
            return "".join(t.get("plain_text", "") for t in title_arr)
    except Exception:
        pass
    return "（无标题）"


# ── notion_append_block ────────────────────────────────────────────────────────

async def notion_append_block(block_id: str, content: str) -> str:
    """
    向指定的 Notion 页面或块追加段落内容。
    对应原来的 mcp__notion__API-patch-block-children。

    参数:
        block_id: 目标页面或块的 ID（可从 notion_search 结果中获取）
        content:  要追加的文本内容，支持多行（每行会成为一个独立段落块）
    """
    # 把多行文本拆分成多个 paragraph 块
    paragraphs = [line for line in content.split("\n") if line.strip()]
    children = [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": para},
                    }
                ]
            },
        }
        for para in paragraphs
    ]

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.patch(
            f"{_NOTION_BASE}/blocks/{block_id}/children",
            headers=_get_headers(),
            json={"children": children},
        )
        resp.raise_for_status()

    added_count = len(resp.json().get("results", []))
    return f"已成功向 Notion 块 {block_id} 追加 {added_count} 个段落。"


# ── Tool Schema ────────────────────────────────────────────────────────────────

NOTION_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "notion_search",
            "description": "在 Notion workspace 中搜索页面和数据库，返回匹配结果的标题、ID 和链接。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notion_append_block",
            "description": "向指定的 Notion 页面追加文字内容（段落块）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "block_id": {
                        "type": "string",
                        "description": "目标 Notion 页面或块的 ID，从 notion_search 结果中获取",
                    },
                    "content": {
                        "type": "string",
                        "description": "要追加的文本内容，多行文本会被拆分为多个段落",
                    },
                },
                "required": ["block_id", "content"],
            },
        },
    },
]

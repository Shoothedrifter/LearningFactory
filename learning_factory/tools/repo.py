"""
tools/repo.py
GitHub 仓库工具实现：封装 zread MCP 服务器。

提供三个工具：
  - repo_structure: 获取仓库目录结构
  - repo_read_file: 读取仓库文件内容
  - repo_search:     搜索仓库文档/issues/commits
"""

from .mcp_client import call_mcp_tool
from ..config import get_zread_url


async def repo_structure(repo_name: str, dir_path: str = "/") -> str:
    """
    获取 GitHub 仓库的目录结构和文件列表。

    参数:
        repo_name: 仓库名称，格式 "owner/repo"，例如 "langchain-ai/langchain"
        dir_path:  目录路径，默认为根目录 "/"
    """
    return await call_mcp_tool(
        server_url=get_zread_url(),
        tool_name="get_repo_structure",
        arguments={"repo_name": repo_name, "dir_path": dir_path},
    )


async def repo_read_file(repo_name: str, file_path: str) -> str:
    """
    读取 GitHub 仓库中指定文件的完整内容。

    参数:
        repo_name: 仓库名称，格式 "owner/repo"
        file_path: 文件的相对路径，例如 "README.md" 或 "src/index.ts"
    """
    return await call_mcp_tool(
        server_url=get_zread_url(),
        tool_name="read_file",
        arguments={"repo_name": repo_name, "file_path": file_path},
    )


async def repo_search(repo_name: str, query: str) -> str:
    """
    搜索 GitHub 仓库的文档、issues 和 commits。

    参数:
        repo_name: 仓库名称，格式 "owner/repo"
        query:      搜索关键词或问题
    """
    return await call_mcp_tool(
        server_url=get_zread_url(),
        tool_name="search_doc",
        arguments={"repo_name": repo_name, "query": query},
    )


# ── Tool Schema ────────────────────────────────────────────────────────────────

REPO_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "repo_structure",
            "description": "获取 GitHub 仓库的目录结构和文件列表，无需克隆仓库。",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_name": {
                        "type": "string",
                        "description": "仓库名称，格式 'owner/repo'，例如 'langchain-ai/langchain'",
                    },
                    "dir_path": {
                        "type": "string",
                        "description": "目录路径，默认为根目录 '/'",
                    },
                },
                "required": ["repo_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "repo_read_file",
            "description": "读取 GitHub 仓库中指定文件的完整内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_name": {
                        "type": "string",
                        "description": "仓库名称，格式 'owner/repo'",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "文件相对路径，例如 'README.md' 或 'src/index.ts'",
                    },
                },
                "required": ["repo_name", "file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "repo_search",
            "description": "搜索 GitHub 仓库的文档、issues 和 commits。",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_name": {
                        "type": "string",
                        "description": "仓库名称，格式 'owner/repo'",
                    },
                    "query": {
                        "type": "string",
                        "description": "搜索关键词或问题",
                    },
                },
                "required": ["repo_name", "query"],
            },
        },
    },
]

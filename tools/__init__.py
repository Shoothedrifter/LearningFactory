"""tools 包：统一导出所有工具函数和 Schema。"""

from .web import web_search, web_fetch, WEB_TOOL_SCHEMAS
from .bash import bash, BASH_TOOL_SCHEMAS
from .notion import notion_search, notion_append_block, NOTION_TOOL_SCHEMAS
from .repo import repo_structure, repo_read_file, repo_search, REPO_TOOL_SCHEMAS
from .filesystem import write_file, append_file, list_directory, FILESYSTEM_TOOL_SCHEMAS
from .skills import load_skill, SKILL_TOOL_SCHEMA

# 工具名称 → 函数的全局映射表
# agent loop 通过这张表把模型返回的函数名映射到实际的 Python 函数
TOOL_REGISTRY = {
    "web_search": web_search,
    "web_fetch": web_fetch,
    "bash": bash,
    "notion_search": notion_search,
    "notion_append_block": notion_append_block,
    "repo_structure": repo_structure,
    "repo_read_file": repo_read_file,
    "repo_search": repo_search,
    "write_file": write_file,
    "append_file": append_file,
    "load_skill": load_skill,
    "list_directory": list_directory,
}

__all__ = [
    "web_search", "web_fetch", "WEB_TOOL_SCHEMAS",
    "bash", "BASH_TOOL_SCHEMAS",
    "notion_search", "notion_append_block", "NOTION_TOOL_SCHEMAS",
    "repo_structure", "repo_read_file", "repo_search", "REPO_TOOL_SCHEMAS",
    "write_file", "append_file", "list_directory", "FILESYSTEM_TOOL_SCHEMAS",
    "load_skill", "SKILL_TOOL_SCHEMA",
    "TOOL_REGISTRY",
]

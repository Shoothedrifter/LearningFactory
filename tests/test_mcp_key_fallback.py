"""
tests/test_mcp_key_fallback.py
MCP 研究工具独立认证通道。MCP_API_KEY 优先，缺省回落 LLM_API_KEY——
模型与研究工具默认同一供应商、一套 Key 共用；供应商对 MCP 单独发 Key 时才需并设。
"""

from learning_factory.tools import mcp_client


def test_mcp_key_takes_priority(monkeypatch):
    monkeypatch.setenv("MCP_API_KEY", "mcp-key")
    monkeypatch.setenv("LLM_API_KEY", "llm-key")
    assert mcp_client._get_mcp_api_key() == "mcp-key"

def test_falls_back_to_llm_key(monkeypatch):
    monkeypatch.delenv("MCP_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "llm-key")
    assert mcp_client._get_mcp_api_key() == "llm-key"

def test_both_missing_is_empty_string(monkeypatch):
    """双缺为空串（不抛）——认证头省略，与 0.1.x 行为一致。"""
    monkeypatch.delenv("MCP_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert mcp_client._get_mcp_api_key() == ""

def test_empty_mcp_key_falls_back(monkeypatch):
    """显式空串视为未设置，回落 LLM Key（or 语义钉住）。"""
    monkeypatch.setenv("MCP_API_KEY", "")
    monkeypatch.setenv("LLM_API_KEY", "llm-key")
    assert mcp_client._get_mcp_api_key() == "llm-key"

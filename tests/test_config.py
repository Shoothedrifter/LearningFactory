"""
tests/test_config.py
配置层测试：LLM_*/MCP_* 环境变量覆盖与默认值（函数式读取，先例 get_output_root_dir）。
旧 GLM_* 名的兼容层测试见 test_legacy_env_compat.py。
"""

import pytest

from learning_factory import config


def test_base_url_default(monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    assert config.get_base_url() == "https://open.bigmodel.cn/api/paas/v4/"

def test_base_url_override(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://proxy.example/v4/")
    assert config.get_base_url() == "https://proxy.example/v4/"

def test_main_model_default_and_override(monkeypatch):
    monkeypatch.delenv("LLM_MAIN_MODEL", raising=False)
    assert config.get_main_agent_model() == "glm-5"
    monkeypatch.setenv("LLM_MAIN_MODEL", "glm-5-airx")
    assert config.get_main_agent_model() == "glm-5-airx"

def test_sub_model_default_and_override(monkeypatch):
    monkeypatch.delenv("LLM_SUB_MODEL", raising=False)
    assert config.get_sub_agent_model() == "glm-5-turbo"
    monkeypatch.setenv("LLM_SUB_MODEL", "glm-5-flash")
    assert config.get_sub_agent_model() == "glm-5-flash"

def test_repo_model_defaults_to_main_tier(monkeypatch):
    monkeypatch.delenv("LLM_REPO_MODEL", raising=False)
    monkeypatch.delenv("LLM_MAIN_MODEL", raising=False)
    assert config.get_repo_analyzer_model() == "glm-5"
    monkeypatch.setenv("LLM_REPO_MODEL", "glm-5-airx")
    assert config.get_repo_analyzer_model() == "glm-5-airx"

@pytest.mark.parametrize("fn,envkey,default", [
    (config.get_web_search_url, "MCP_WEB_SEARCH_URL",
     "https://open.bigmodel.cn/api/mcp/web_search_prime/mcp"),
    (config.get_web_reader_url, "MCP_WEB_READER_URL",
     "https://open.bigmodel.cn/api/mcp/web_reader/mcp"),
    (config.get_zread_url, "MCP_ZREAD_URL",
     "https://open.bigmodel.cn/api/mcp/zread/mcp"),
])
def test_mcp_urls_default_and_override(fn, envkey, default, monkeypatch):
    monkeypatch.delenv(envkey, raising=False)
    assert fn() == default
    monkeypatch.setenv(envkey, "https://mcp.example/mcp")
    assert fn() == "https://mcp.example/mcp"

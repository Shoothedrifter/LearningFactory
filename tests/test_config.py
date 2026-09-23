"""
tests/test_config.py
配置层测试：GLM_* 环境变量覆盖与默认值（函数式读取，先例 get_output_root_dir）。
"""

import pytest

from learning_factory import config


def test_base_url_default(monkeypatch):
    monkeypatch.delenv("GLM_BASE_URL", raising=False)
    assert config.get_glm_base_url() == "https://open.bigmodel.cn/api/paas/v4/"

def test_base_url_override(monkeypatch):
    monkeypatch.setenv("GLM_BASE_URL", "https://proxy.example/v4/")
    assert config.get_glm_base_url() == "https://proxy.example/v4/"

def test_main_model_default_and_override(monkeypatch):
    monkeypatch.delenv("GLM_MAIN_MODEL", raising=False)
    assert config.get_main_agent_model() == "glm-5"
    monkeypatch.setenv("GLM_MAIN_MODEL", "glm-5-airx")
    assert config.get_main_agent_model() == "glm-5-airx"

def test_sub_model_default_and_override(monkeypatch):
    monkeypatch.delenv("GLM_SUB_MODEL", raising=False)
    assert config.get_sub_agent_model() == "glm-5-turbo"
    monkeypatch.setenv("GLM_SUB_MODEL", "glm-5-flash")
    assert config.get_sub_agent_model() == "glm-5-flash"

def test_repo_model_defaults_to_main_tier(monkeypatch):
    monkeypatch.delenv("GLM_REPO_MODEL", raising=False)
    monkeypatch.delenv("GLM_MAIN_MODEL", raising=False)
    assert config.get_repo_analyzer_model() == "glm-5"
    monkeypatch.setenv("GLM_REPO_MODEL", "glm-5-airx")
    assert config.get_repo_analyzer_model() == "glm-5-airx"

@pytest.mark.parametrize("fn,envkey,default", [
    (config.get_web_search_url, "GLM_MCP_WEB_SEARCH_URL",
     "https://open.bigmodel.cn/api/mcp/web_search_prime/mcp"),
    (config.get_web_reader_url, "GLM_MCP_WEB_READER_URL",
     "https://open.bigmodel.cn/api/mcp/web_reader/mcp"),
    (config.get_zread_url, "GLM_MCP_ZREAD_URL",
     "https://open.bigmodel.cn/api/mcp/zread/mcp"),
])
def test_mcp_urls_default_and_override(fn, envkey, default, monkeypatch):
    monkeypatch.delenv(envkey, raising=False)
    assert fn() == default
    monkeypatch.setenv(envkey, "https://mcp.example/mcp")
    assert fn() == "https://mcp.example/mcp"

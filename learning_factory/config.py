"""
learning_factory/config.py
运行配置层：base_url / 模型名 / MCP 端点集中读取口，环境变量 LLM_*/MCP_* 可覆盖。

此前 8 处硬编码散布（agent.py×2、base.py、subagents.py×3、web.py×2、repo.py），
换端点（自建代理/兼容网关）或切模型需逐处找改。函数式每次读 env：
.env 运行时生效、测试可直接 monkeypatch（同 get_output_root_dir 先例）。
LLM_API_KEY 不在此层（启动校验见 agent.ensure_api_key）。
"""

import os

_DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"


def get_base_url() -> str:
    """模型供应商 OpenAI 兼容端点（LLM_BASE_URL 可覆盖，默认智谱 GLM）。"""
    return os.environ.get("LLM_BASE_URL", _DEFAULT_BASE_URL)


def get_main_agent_model() -> str:
    """主 Agent 模型（LLM_MAIN_MODEL 可覆盖，默认 glm-5）。"""
    return os.environ.get("LLM_MAIN_MODEL", "glm-5")


def get_sub_agent_model() -> str:
    """子 Agent 通用模型（LLM_SUB_MODEL 可覆盖，默认 glm-5-turbo）。"""
    return os.environ.get("LLM_SUB_MODEL", "glm-5-turbo")


def get_repo_analyzer_model() -> str:
    """repo_analyzer 专用模型（LLM_REPO_MODEL 可覆盖，默认 glm-5——仓库分析需要更强模型可靠调用工具）。"""
    return os.environ.get("LLM_REPO_MODEL", "glm-5")


def get_web_search_url() -> str:
    """MCP 网页搜索端点（MCP_WEB_SEARCH_URL 可覆盖）。"""
    return os.environ.get("MCP_WEB_SEARCH_URL",
                          "https://open.bigmodel.cn/api/mcp/web_search_prime/mcp")


def get_web_reader_url() -> str:
    """MCP 网页抓取端点（MCP_WEB_READER_URL 可覆盖）。"""
    return os.environ.get("MCP_WEB_READER_URL",
                          "https://open.bigmodel.cn/api/mcp/web_reader/mcp")


def get_zread_url() -> str:
    """MCP GitHub 仓库读取端点（MCP_ZREAD_URL 可覆盖）。"""
    return os.environ.get("MCP_ZREAD_URL",
                          "https://open.bigmodel.cn/api/mcp/zread/mcp")


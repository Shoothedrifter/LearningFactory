"""
learning_factory/config.py
运行配置层：base_url / 模型名 / MCP 端点集中读取口，环境变量 LLM_*/MCP_* 可覆盖
（旧 GLM_* 名的兼容映射见 migrate_legacy_env，Task 2 加入）。

此前 8 处硬编码散布（agent.py×2、base.py、subagents.py×3、web.py×2、repo.py），
换端点（自建代理/兼容网关）或切模型需逐处找改。函数式每次读 env：
.env 运行时生效、测试可直接 monkeypatch（同 get_output_root_dir 先例）。
GLM_API_KEY 不在此层（启动校验见 agent.ensure_api_key）。
"""

import os
import sys

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


# ── 旧变量名兼容层（0.1.x GLM_* → 0.2.0 LLM_*/MCP_*）───────────────────────────
# 旧 .env 不破：启动时一次性把旧名值搬进新名并删除旧名（幂等），命中时打一行
# 迁移提示。挂 ensure_api_key 开头（CLI/Web 双入口唯一必经点，晚于两处
# load_dotenv）。此后进程内全部代码只读新名——本文件是全仓唯一允许出现
# GLM_ 字面量的地方（tests/test_legacy_env_compat.py 钉住）。
_LEGACY_ENV_MAP = {
    "GLM_API_KEY": "LLM_API_KEY",
    "GLM_BASE_URL": "LLM_BASE_URL",
    "GLM_MAIN_MODEL": "LLM_MAIN_MODEL",
    "GLM_SUB_MODEL": "LLM_SUB_MODEL",
    "GLM_REPO_MODEL": "LLM_REPO_MODEL",
    "GLM_MCP_WEB_SEARCH_URL": "MCP_WEB_SEARCH_URL",
    "GLM_MCP_WEB_READER_URL": "MCP_WEB_READER_URL",
    "GLM_MCP_ZREAD_URL": "MCP_ZREAD_URL",
}


def migrate_legacy_env() -> None:
    """
    旧 GLM_* 变量一次性映射到新名（幂等：迁移后删旧名，重复调用无命中）。

    旧名有值且新名未设 → 搬值并删除旧名；新名已设时旧名忽略（新名优先，
    不覆盖不删除）。有命中时向 stderr 打恰好一行迁移提示。
    """
    migrated = []
    for old, new in _LEGACY_ENV_MAP.items():
        if old in os.environ and new not in os.environ:
            os.environ[new] = os.environ[old]
            del os.environ[old]
            migrated.append(old)
    if migrated:
        print(f"[兼容] 检测到旧变量名 {', '.join(migrated)}，已按新名读取；"
              f"建议更新 .env 改用 LLM_*/MCP_* 命名", file=sys.stderr)

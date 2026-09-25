"""
tests/test_model_config.py
模型配置钉住测试：模型名直接影响能力档与计费，防止静默漂移。
2026-09-24 配置层化：默认值钉在 config 函数，调用点经 config 读取。
"""

from learning_factory import config


def test_main_agent_model_default(monkeypatch):
    """主 Agent 默认模型钉住：glm-5。"""
    monkeypatch.delenv("LLM_MAIN_MODEL", raising=False)
    assert config.get_main_agent_model() == "glm-5"


def test_sub_agent_model_default(monkeypatch):
    """子 Agent 默认模型钉住：glm-5-turbo。"""
    monkeypatch.delenv("LLM_SUB_MODEL", raising=False)
    assert config.get_sub_agent_model() == "glm-5-turbo"


def test_repo_analyzer_model_default(monkeypatch):
    """repo_analyzer 默认模型钉住：glm-5。"""
    monkeypatch.delenv("LLM_REPO_MODEL", raising=False)
    assert config.get_repo_analyzer_model() == "glm-5"

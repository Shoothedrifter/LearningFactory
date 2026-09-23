"""
tests/test_model_config.py
模型配置钉住测试：模型名直接影响能力档与计费，防止静默漂移。
2026-09-19 从 glm-4-plus / glm-4-flash 迁移到 glm-5 / glm-5-turbo。
"""

from multi_agent import agent
from multi_agent.agents import base
from multi_agent.agents import subagents


def test_main_agent_model_is_glm5():
    """主 Agent 模型钉住：glm-5。"""
    assert agent.MAIN_AGENT_MODEL == "glm-5"


def test_default_model_is_glm5():
    """base 默认模型钉住：glm-5。"""
    assert base.DEFAULT_MODEL == "glm-5"


def test_sub_agent_model_is_glm5_turbo():
    """子 Agent 默认模型钉住：glm-5-turbo。"""
    assert subagents._SUB_AGENT_MODEL == "glm-5-turbo"

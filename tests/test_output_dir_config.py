"""
tests/test_output_dir_config.py
技能产物输出根目录可配（CLI 化缺口 #7）。

Learning-Factory/ 原本硬编码于 enforcement、两版兜底文案与
SKILL.md 正文（经 load_skill 注入）共四个通道；现统一经环境变量
MULTI_AGENT_OUTPUT_DIR（CLI --output-dir 的落地通道）覆盖，
默认仍为 Learning-Factory/。本测试钉住四个注入点，防止部分生效
（模型看到两个目录指示会写错位置）。
"""

from helpers import make_tool_call, make_tool_calls_response, make_text_response

from multi_agent import agent
from multi_agent.tools import skills as skills_mod


def test_enforcement_honors_output_dir_env(monkeypatch):
    """enforcement（load_skills 产物）注入自定义根目录，默认值不再出现。"""
    monkeypatch.setenv("MULTI_AGENT_OUTPUT_DIR", "MyFactory")
    text = agent.load_skills()
    assert "MyFactory/learning-" in text
    assert "Learning-Factory" not in text


def test_enforcement_defaults_to_learning_factory(monkeypatch):
    """未设置环境变量时保持默认目录（防回归）。"""
    monkeypatch.delenv("MULTI_AGENT_OUTPUT_DIR", raising=False)
    text = agent.load_skills()
    assert "Learning-Factory/learning-" in text


async def test_load_skill_text_honors_output_dir_env(monkeypatch):
    """SKILL.md 全文（load_skill 产物）同步注入，避免与 enforcement 冲突。"""
    monkeypatch.setenv("MULTI_AGENT_OUTPUT_DIR", "MyFactory")
    text = await skills_mod.load_skill("learning-a-tool")
    assert "MyFactory/learning-{tool-name}/" in text
    assert "Learning-Factory" not in text


async def test_fallback_copy_honors_output_dir_env(patch_openai, monkeypatch):
    """普通版兜底总结消息注入自定义根目录。"""
    monkeypatch.setattr(agent, "MAX_ROUNDS", 1)
    monkeypatch.setenv("MULTI_AGENT_OUTPUT_DIR", "MyFactory")
    client = patch_openai(
        make_tool_calls_response([make_tool_call("c1", "unknown_tool", x=1)]),
        make_text_response("总结"),
    )

    await agent.run_main_agent(
        system_prompt="测试",
        messages=[{"role": "user", "content": "干活"}],
        sub_prompts={},
    )

    msg = client.chat.completions.create.call_args_list[1].kwargs["messages"][-1]["content"]
    assert "MyFactory/" in msg
    assert "Learning-Factory" not in msg


async def test_stream_fallback_copy_honors_output_dir_env(patch_openai, monkeypatch):
    """流式版兜底总结消息同样注入（与普通版对齐）。"""
    monkeypatch.setattr(agent, "MAX_ROUNDS", 1)
    monkeypatch.setenv("MULTI_AGENT_OUTPUT_DIR", "MyFactory")
    client = patch_openai(
        make_tool_calls_response([make_tool_call("c1", "unknown_tool", x=1)]),
        make_text_response("流式总结"),
    )

    async for _ in agent.run_main_agent_stream(
        system_prompt="测试",
        messages=[{"role": "user", "content": "干活"}],
        sub_prompts={},
    ):
        pass

    msg = client.chat.completions.create.call_args_list[1].kwargs["messages"][-1]["content"]
    assert "MyFactory/" in msg
    assert "Learning-Factory" not in msg

"""
tests/test_max_rounds_fallback.py
主 Agent 达到最大轮次时兜底总结的 TDD 测试。

普通版为新增行为（先红后绿）；流式版已有该行为，测试用于钉住防回归。
用 unknown_tool 避免真实执行任何工具（_run_plain_tool 对未知工具返回错误串）。
"""

import json

from helpers import make_tool_call, make_tool_calls_response, make_text_response

from multi_agent import agent


async def test_main_agent_summarizes_on_round_exhaustion(patch_openai, monkeypatch):
    """普通版：轮次耗尽后必须发起一次无 tools 的总结调用并返回其文本。"""
    monkeypatch.setattr(agent, "MAX_ROUNDS", 1)
    client = patch_openai(
        make_tool_calls_response([make_tool_call("c1", "unknown_tool", x=1)]),
        make_text_response("基于已有信息的总结"),
    )

    answer = await agent.run_main_agent(
        system_prompt="测试",
        messages=[{"role": "user", "content": "干活"}],
        sub_prompts={},
    )

    assert answer == "基于已有信息的总结"
    # 总结调用必须禁用工具（tools=None），保证模型只能输出文本
    summary_call = client.chat.completions.create.call_args_list[1]
    assert summary_call.kwargs.get("tools") is None
    # 总结请求末尾携带"不要再调用工具"的引导消息
    msgs = summary_call.kwargs["messages"]
    assert msgs[-1]["role"] == "user"
    assert "不要再调用任何工具" in msgs[-1]["content"]
    # 续写路径锚点：兜底总结必须强制完整相对路径，防总结文本省略目录前缀
    assert "完整相对路径" in msgs[-1]["content"]
    assert "Learning-Factory" in msgs[-1]["content"]


async def test_stream_summarizes_on_round_exhaustion(patch_openai, monkeypatch):
    """流式版：既有兜底行为钉住——耗尽后产出总结 answer 事件（防回归）。"""
    monkeypatch.setattr(agent, "MAX_ROUNDS", 1)
    client = patch_openai(
        make_tool_calls_response([make_tool_call("c1", "unknown_tool", x=1)]),
        make_text_response("流式总结"),
    )

    events = [
        json.loads(ev)
        async for ev in agent.run_main_agent_stream(
            system_prompt="测试",
            messages=[{"role": "user", "content": "干活"}],
            sub_prompts={},
        )
    ]

    answers = [e for e in events if e["type"] == "answer" and e.get("agent") == "main"]
    assert answers and answers[-1]["content"] == "流式总结"
    # 流式版兜底消息同样携带完整相对路径要求（与普通版对齐）
    summary_call = client.chat.completions.create.call_args_list[1]
    assert "完整相对路径" in summary_call.kwargs["messages"][-1]["content"]


async def test_main_agent_summary_claims_aligned_with_tool_results(patch_openai, monkeypatch):
    """普通版：兜底消息强制只以工具结果判定完成状态（真实性条款）。"""
    monkeypatch.setattr(agent, "MAX_ROUNDS", 1)
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
    assert "只以工具结果为准" in msg
    assert "[成功]" in msg and "[错误]" in msg
    assert "一律列为未完成" in msg


async def test_stream_summary_claims_aligned_with_tool_results(patch_openai, monkeypatch):
    """流式版：兜底消息同样携带真实性条款（与普通版对齐）。"""
    monkeypatch.setattr(agent, "MAX_ROUNDS", 1)
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
    assert "只以工具结果为准" in msg
    assert "[成功]" in msg and "[错误]" in msg
    assert "一律列为未完成" in msg

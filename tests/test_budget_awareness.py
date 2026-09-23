"""
tests/test_budget_awareness.py
主 Agent 两版本每轮注入剩余轮次预算提示的 TDD 测试（follow up B）。
"""

import json

from multi_agent import agent
from helpers import make_text_response, make_tool_call, make_tool_calls_response


def _system_content(call):
    """取出一次 LLM 调用请求中的 system 消息内容。"""
    return call.kwargs["messages"][0]["content"]


async def test_plain_requests_carry_round_budget(patch_openai):
    """普通版：每轮请求的 system 尾部携带轮次进度与剩余数，原 prompt 不被破坏。"""
    client = patch_openai(
        make_tool_calls_response([make_tool_call("c1", "unknown_tool", x=1)]),
        make_tool_calls_response([make_tool_call("c2", "unknown_tool", x=1)]),
        make_text_response("完成"),
    )
    await agent.run_main_agent(
        system_prompt="测试",
        messages=[{"role": "user", "content": "随便"}],
        sub_prompts={},
    )
    calls = client.chat.completions.create.call_args_list
    assert len(calls) == 3  # 两轮工具 + 一轮文本
    for idx, call in enumerate(calls, start=1):
        content = _system_content(call)
        assert f"Round {idx}/{agent.MAX_ROUNDS}" in content  # 轮次进度（禁止硬编码 12）
        assert "测试" in content                             # 原 system prompt 完整保留


async def test_stream_requests_carry_round_budget(patch_openai):
    """流式版：同款预算注入（与普通版对齐）。"""
    client = patch_openai(
        make_tool_calls_response([make_tool_call("c1", "unknown_tool", x=1)]),
        make_text_response("流式完成"),
    )
    events = [
        json.loads(ev)
        async for ev in agent.run_main_agent_stream(
            system_prompt="测试",
            messages=[{"role": "user", "content": "干活"}],
            sub_prompts={},
        )
    ]
    assert events  # 消费完生成器
    calls = client.chat.completions.create.call_args_list
    assert len(calls) == 2  # 一轮工具 + 一轮文本
    assert f"Round 1/{agent.MAX_ROUNDS}" in _system_content(calls[0])
    assert f"Round 2/{agent.MAX_ROUNDS}" in _system_content(calls[1])
    assert "测试" in _system_content(calls[0])

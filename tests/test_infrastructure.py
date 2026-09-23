"""
tests/test_infrastructure.py
验证测试基础设施本身：
  1. 假响应结构与 agent.py 实际读取的字段一致；
  2. patch_openai 能让真实的 run_main_agent 走通一轮"纯文本回答"。
（tests/ 目录无 __init__.py，pytest 会把本目录加入 sys.path，故直接 import helpers。）
"""

import json

from helpers import ConcurrencyRecorder, make_tool_call, make_tool_calls_response, make_text_response

from multi_agent import agent


def test_make_tool_call_shape():
    tc = make_tool_call("call_1", "dispatch_to_subagent", agent_name="docs_researcher", task="查文档")
    assert tc.id == "call_1"
    assert tc.function.name == "dispatch_to_subagent"
    args = json.loads(tc.function.arguments)
    assert args["agent_name"] == "docs_researcher"
    assert args["task"] == "查文档"


def test_response_shapes():
    tool_resp = make_tool_calls_response([make_tool_call("c1", "bash", cmd="ls")])
    choice = tool_resp.choices[0]
    assert choice.finish_reason == "tool_calls"
    assert choice.message.tool_calls[0].id == "c1"
    assert choice.message.content is None

    text_resp = make_text_response("答案")
    assert text_resp.choices[0].finish_reason == "stop"
    assert text_resp.choices[0].message.content == "答案"
    assert text_resp.choices[0].message.tool_calls is None


def test_concurrency_recorder_tracks_peak():
    rec = ConcurrencyRecorder()
    rec.enter()
    rec.enter()
    rec.exit()
    assert rec.max_active == 2
    assert rec.active == 1


async def test_patch_openai_works_with_real_function(patch_openai):
    """用真实 run_main_agent 做冒烟：一轮纯文本回答即可返回，验证伪造结构正确。"""
    client = patch_openai(make_text_response("好的"))
    answer = await agent.run_main_agent(
        system_prompt="测试",
        messages=[{"role": "user", "content": "你好"}],
        sub_prompts={},
    )
    assert answer == "好的"
    assert client.chat.completions.create.await_count == 1

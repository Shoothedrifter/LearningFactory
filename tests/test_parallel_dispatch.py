"""
tests/test_parallel_dispatch.py
run_main_agent 同轮多工具调用并行执行的 TDD 测试。

核心断言原理：用 ConcurrencyRecorder 记录假子 Agent runner 的并发峰值。
串行实现下峰值恒为 1；asyncio.gather 并行实现下峰值 = 同轮调用数。
"""

import asyncio
from types import SimpleNamespace

from helpers import ConcurrencyRecorder, make_tool_call, make_tool_calls_response, make_text_response

import agent


def _dispatch_call(call_id: str, agent_name: str, task: str = "研究任务"):
    """构造一个 dispatch_to_subagent 的 tool_call。"""
    return make_tool_call(call_id, "dispatch_to_subagent", agent_name=agent_name, task=task)


def _make_runners(recorder: ConcurrencyRecorder):
    """构造 3 个记录并发度的假子 Agent runner（签名与真实 runner 一致：(task, prompt)）。"""

    def make(name: str):
        async def runner(task: str, prompt: str) -> str:
            recorder.enter()
            await asyncio.sleep(0.05)
            recorder.exit()
            return f"{name} 的研究结果"

        return runner

    return {name: make(name) for name in ("docs_researcher", "repo_analyzer", "web_researcher")}


async def test_same_round_dispatches_run_concurrently(patch_openai, monkeypatch):
    """同一轮返回的 3 个 dispatch_to_subagent 必须并发执行（峰值并发度 = 3）。"""
    recorder = ConcurrencyRecorder()
    monkeypatch.setattr(agent, "SUBAGENT_RUNNERS", _make_runners(recorder))
    patch_openai(
        make_tool_calls_response([
            _dispatch_call("call_1", "docs_researcher"),
            _dispatch_call("call_2", "repo_analyzer"),
            _dispatch_call("call_3", "web_researcher"),
        ]),
        make_text_response("最终答案"),
    )

    answer = await agent.run_main_agent(
        system_prompt="测试",
        messages=[{"role": "user", "content": "研究一下"}],
        sub_prompts={},
    )

    assert answer == "最终答案"
    assert recorder.max_active == 3  # 串行实现下 max_active == 1 → 此测试先失败


async def test_tool_results_appended_in_protocol_order(patch_openai, monkeypatch):
    """每个 tool_call_id 都必须按顺序回填 role=tool 消息（OpenAI 消息协议完整性）。"""
    recorder = ConcurrencyRecorder()
    monkeypatch.setattr(agent, "SUBAGENT_RUNNERS", _make_runners(recorder))
    client = patch_openai(
        make_tool_calls_response([
            _dispatch_call("call_1", "docs_researcher"),
            _dispatch_call("call_2", "web_researcher"),
        ]),
        make_text_response("完成"),
    )

    await agent.run_main_agent(
        system_prompt="测试",
        messages=[{"role": "user", "content": "研究一下"}],
        sub_prompts={},
    )

    # 第 2 次模型调用的 messages 结构：[system, user, assistant(带 2 个 tool_calls), tool, tool]
    second_call_messages = client.chat.completions.create.call_args_list[1].kwargs["messages"]
    assert second_call_messages[2]["role"] == "assistant"
    assert len(second_call_messages[2]["tool_calls"]) == 2
    tool_msgs = second_call_messages[3:5]
    assert [m["tool_call_id"] for m in tool_msgs] == ["call_1", "call_2"]
    assert "docs_researcher 的研究结果" in tool_msgs[0]["content"]
    assert "web_researcher 的研究结果" in tool_msgs[1]["content"]


async def test_one_tool_failure_does_not_break_others(patch_openai, monkeypatch):
    """单个子 Agent 抛异常时，错误成为该工具的结果字符串，其余工具不受影响。"""

    async def boom(task: str, prompt: str) -> str:
        raise RuntimeError("子 Agent 崩了")

    runners = _make_runners(ConcurrencyRecorder())
    runners["repo_analyzer"] = boom
    monkeypatch.setattr(agent, "SUBAGENT_RUNNERS", runners)
    client = patch_openai(
        make_tool_calls_response([
            _dispatch_call("call_1", "docs_researcher"),
            _dispatch_call("call_2", "repo_analyzer"),
            _dispatch_call("call_3", "web_researcher"),
        ]),
        make_text_response("部分成功的总结"),
    )

    answer = await agent.run_main_agent(
        system_prompt="测试",
        messages=[{"role": "user", "content": "研究一下"}],
        sub_prompts={},
    )

    assert answer == "部分成功的总结"
    tool_msgs = client.chat.completions.create.call_args_list[1].kwargs["messages"][3:6]
    assert "docs_researcher 的研究结果" in tool_msgs[0]["content"]
    assert "[错误]" in tool_msgs[1]["content"]
    assert "子 Agent 崩了" in tool_msgs[1]["content"]
    assert "web_researcher 的研究结果" in tool_msgs[2]["content"]


async def test_malformed_arguments_become_error_result(patch_openai, monkeypatch):
    """畸形 JSON 参数：错误成为该工具的结果字符串，其余工具照常，整轮不被炸掉。"""
    bad_call = SimpleNamespace(
        id="call_bad",
        function=SimpleNamespace(
            name="dispatch_to_subagent",
            arguments='{"agent_name": "docs_researcher", "task": ',  # 截断的 JSON
        ),
    )
    recorder = ConcurrencyRecorder()
    monkeypatch.setattr(agent, "SUBAGENT_RUNNERS", _make_runners(recorder))
    client = patch_openai(
        make_tool_calls_response([bad_call, _dispatch_call("call_ok", "web_researcher")]),
        make_text_response("收尾"),
    )

    answer = await agent.run_main_agent(
        system_prompt="测试",
        messages=[{"role": "user", "content": "研究一下"}],
        sub_prompts={},
    )

    assert answer == "收尾"
    tool_msgs = client.chat.completions.create.call_args_list[1].kwargs["messages"][3:5]
    assert "工具参数解析失败" in tool_msgs[0]["content"]
    # 引导文案：解析失败时必须引导模型缩短参数改走 file_writer，而非盲目重试同样的超长参数
    assert "file_writer" in tool_msgs[0]["content"]
    assert "缩短" in tool_msgs[0]["content"]
    assert "web_researcher 的研究结果" in tool_msgs[1]["content"]

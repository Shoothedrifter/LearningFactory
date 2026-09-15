"""
tests/test_parallel_dispatch_stream.py
run_main_agent_stream 同轮多子 Agent 并行执行的 TDD 测试。

假流式 runner 是异步生成器（yield 事件字符串），签名与真实 runner 一致。
"""

import asyncio
import json

from helpers import ConcurrencyRecorder, make_tool_call, make_tool_calls_response, make_text_response

import agent


def _dispatch_call(call_id: str, agent_name: str, task: str = "研究任务"):
    return make_tool_call(call_id, "dispatch_to_subagent", agent_name=agent_name, task=task)


def _make_stream_runners(recorder: ConcurrencyRecorder):
    """构造假的流式子 Agent：yield status/answer 事件 + 记录并发度。"""

    def make(name: str):
        async def runner(task: str, prompt: str):
            recorder.enter()
            yield json.dumps(
                {"type": "status", "agent": name, "message": f"{name} 工作中"},
                ensure_ascii=False,
            )
            await asyncio.sleep(0.05)
            yield json.dumps(
                {"type": "answer", "agent": name, "content": f"{name} 的结论"},
                ensure_ascii=False,
            )
            recorder.exit()

        return runner

    return {name: make(name) for name in ("docs_researcher", "repo_analyzer", "web_researcher")}


async def _collect_events(**kwargs):
    """收集 run_main_agent_stream yield 的全部事件并解析为 dict。"""
    return [json.loads(ev) async for ev in agent.run_main_agent_stream(**kwargs)]


def _run_stream_setup(patch_openai, monkeypatch, recorder):
    """公共 setup：3 个同轮 dispatch + 第 2 轮纯文本收尾。"""
    monkeypatch.setattr(agent, "SUBAGENT_STREAM_RUNNERS", _make_stream_runners(recorder))
    client = patch_openai(
        make_tool_calls_response([
            _dispatch_call("call_1", "docs_researcher"),
            _dispatch_call("call_2", "repo_analyzer"),
            _dispatch_call("call_3", "web_researcher"),
        ]),
        make_text_response("最终答案"),
    )
    return client


async def test_stream_dispatches_run_concurrently(patch_openai, monkeypatch):
    """流式版：同一轮 3 个子 Agent 并发执行，主 Agent 最终答案正常产出。"""
    recorder = ConcurrencyRecorder()
    _run_stream_setup(patch_openai, monkeypatch, recorder)

    events = await _collect_events(
        system_prompt="测试",
        messages=[{"role": "user", "content": "研究一下"}],
        sub_prompts={},
    )

    assert recorder.max_active == 3  # 串行实现下 == 1 → 此测试先失败
    answer_events = [e for e in events if e["type"] == "answer" and e.get("agent") == "main"]
    assert answer_events[-1]["content"] == "最终答案"


async def test_stream_all_starts_before_any_done(patch_openai, monkeypatch):
    """3 个 subagent start 事件必须全部先于第一个 done 事件（证明同时启动而非排队）。"""
    recorder = ConcurrencyRecorder()
    _run_stream_setup(patch_openai, monkeypatch, recorder)

    events = await _collect_events(
        system_prompt="测试",
        messages=[{"role": "user", "content": "研究一下"}],
        sub_prompts={},
    )

    sub_events = [e for e in events if e["type"] == "subagent"]
    statuses = [e["status"] for e in sub_events]
    # 串行实现下为 start,done,start,done,start,done → 此断言先失败
    assert statuses[:3] == ["start", "start", "start"]
    assert statuses[3:] == ["done", "done", "done"]


async def test_stream_subagent_answers_become_tool_result(patch_openai, monkeypatch):
    """子 Agent 的 answer 事件内容必须汇总为工具结果回填消息历史（协议完整性）。"""
    recorder = ConcurrencyRecorder()
    monkeypatch.setattr(agent, "SUBAGENT_STREAM_RUNNERS", _make_stream_runners(recorder))
    client = patch_openai(
        make_tool_calls_response([_dispatch_call("call_1", "docs_researcher")]),
        make_text_response("ok"),
    )

    await _collect_events(
        system_prompt="测试",
        messages=[{"role": "user", "content": "研究一下"}],
        sub_prompts={},
    )

    # 第 2 次模型调用：[system, user, assistant, tool]
    tool_msg = client.chat.completions.create.call_args_list[1].kwargs["messages"][3]
    assert tool_msg["role"] == "tool"
    assert tool_msg["tool_call_id"] == "call_1"
    assert "docs_researcher 的结论" in tool_msg["content"]

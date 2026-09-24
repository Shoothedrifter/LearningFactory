"""
tests/test_parallel_dispatch_stream.py
run_main_agent_stream 同轮多子 Agent 并行执行的 TDD 测试。

假流式 runner 是异步生成器（yield 事件字符串），签名与真实 runner 一致。
"""

import asyncio
import json
from types import SimpleNamespace

from helpers import ConcurrencyRecorder, make_tool_call, make_tool_calls_response, make_text_response

from learning_factory import agent


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

    assert recorder.max_active == min(3, agent._DISPATCH_CONCURRENCY_LIMIT)
    # 并行性保持（串行实现下 == 1）；2026-09-23 起受节流上限约束，
    # 2026-09-24 上限 3→2，3 路同轮为 2+1 波、峰值即上限
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
    # 事件来源说明：subagent start/done 由主 Agent 调度层统一发送；
    # 子 Agent 流式 runner 只转发内部过程事件（去重后与本测试的假
    # runner 同构），故生产流中 subagent 事件也恰为 3 start + 3 done。
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


def _make_stream_runners_with_failure(failing_name: str):
    """三个假流式 runner，failing_name 那个在产出 answer 前崩溃。"""

    def make(name: str):
        async def runner(task: str, prompt: str):
            yield json.dumps(
                {"type": "status", "agent": name, "message": f"{name} 工作中"},
                ensure_ascii=False,
            )
            if name == failing_name:
                raise RuntimeError("子 Agent 流式崩溃")
            await asyncio.sleep(0.05)
            yield json.dumps(
                {"type": "answer", "agent": name, "content": f"{name} 的结论"},
                ensure_ascii=False,
            )

        return runner

    return {name: make(name) for name in ("docs_researcher", "repo_analyzer", "web_researcher")}


async def test_stream_one_subagent_failure_does_not_break_others(patch_openai, monkeypatch):
    """流式版：单个子 Agent 崩溃只影响自身结果，其余照常、主 Agent 正常收尾。"""
    monkeypatch.setattr(agent, "SUBAGENT_STREAM_RUNNERS", _make_stream_runners_with_failure("repo_analyzer"))
    client = patch_openai(
        make_tool_calls_response([
            _dispatch_call("call_1", "docs_researcher"),
            _dispatch_call("call_2", "repo_analyzer"),
            _dispatch_call("call_3", "web_researcher"),
        ]),
        make_text_response("部分成功的总结"),
    )

    events = await _collect_events(
        system_prompt="测试",
        messages=[{"role": "user", "content": "研究一下"}],
        sub_prompts={},
    )

    # 主 Agent 正常收尾
    answer_events = [e for e in events if e["type"] == "answer" and e.get("agent") == "main"]
    assert answer_events[-1]["content"] == "部分成功的总结"
    # 崩溃的子 Agent 也补齐了 done 事件（前端不卡"进行中"）
    sub_events = [e for e in events if e["type"] == "subagent"]
    assert [e["status"] for e in sub_events].count("done") == 3
    # 工具结果回填：成功的进结论、失败的进错误串
    tool_msgs = client.chat.completions.create.call_args_list[1].kwargs["messages"][3:6]
    assert "docs_researcher 的结论" in tool_msgs[0]["content"]
    assert "[错误]" in tool_msgs[1]["content"]
    assert "子 Agent 流式崩溃" in tool_msgs[1]["content"]
    assert "web_researcher 的结论" in tool_msgs[2]["content"]


async def test_stream_done_event_carries_ok_flag(patch_openai, monkeypatch):
    """done 事件带成败 ok 字段：崩溃子 Agent ok=False、正常子 Agent ok=True。

    实测病灶（logs/ai-agent_CLI.txt）：429 耗尽的子 Agent 也渲染 ✔ 完成，
    与最终总结「❌ 未执行成功」观感矛盾。判据为工具结果 [错误] 前缀
    （参数无效/未知子 Agent/429 耗尽/执行异常的统一回填前缀）。
    """
    monkeypatch.setattr(agent, "SUBAGENT_STREAM_RUNNERS",
                        _make_stream_runners_with_failure("repo_analyzer"))
    patch_openai(
        make_tool_calls_response([
            _dispatch_call("call_1", "docs_researcher"),
            _dispatch_call("call_2", "repo_analyzer"),
        ]),
        make_text_response("总结"),
    )

    events = await _collect_events(
        system_prompt="测试",
        messages=[{"role": "user", "content": "研究一下"}],
        sub_prompts={},
    )

    done = {e["subagent"]: e for e in events
            if e["type"] == "subagent" and e["status"] == "done"}
    assert done["docs_researcher"].get("ok") is True
    assert done["repo_analyzer"].get("ok") is False


async def test_stream_malformed_arguments_do_not_break_round(patch_openai, monkeypatch):
    """流式版：畸形 JSON 参数成为错误结果，事件流与整轮不受影响。"""
    bad_call = SimpleNamespace(
        id="call_bad",
        function=SimpleNamespace(
            name="dispatch_to_subagent",
            arguments='{"agent_name": ',  # 截断的 JSON
        ),
    )
    monkeypatch.setattr(agent, "SUBAGENT_STREAM_RUNNERS", _make_stream_runners(ConcurrencyRecorder()))
    client = patch_openai(
        make_tool_calls_response([bad_call]),
        make_text_response("收尾"),
    )

    events = await _collect_events(
        system_prompt="测试",
        messages=[{"role": "user", "content": "研究一下"}],
        sub_prompts={},
    )

    answer_events = [e for e in events if e["type"] == "answer" and e.get("agent") == "main"]
    assert answer_events[-1]["content"] == "收尾"
    tool_msg = client.chat.completions.create.call_args_list[1].kwargs["messages"][3]
    assert "[错误]" in tool_msg["content"]


async def test_stream_plain_tool_malformed_arguments_hint(patch_openai):
    """流式版：普通工具畸形 JSON 参数返回带分块引导的错误串（与普通版文案一致）。"""
    bad_call = SimpleNamespace(
        id="call_bad",
        function=SimpleNamespace(
            name="write_file",
            arguments='{"path": "a.md", "content": "第',  # 截断的 JSON
        ),
    )
    client = patch_openai(
        make_tool_calls_response([bad_call]),
        make_text_response("收尾"),
    )

    events = await _collect_events(
        system_prompt="测试",
        messages=[{"role": "user", "content": "写文件"}],
        sub_prompts={},
    )

    answer_events = [e for e in events if e["type"] == "answer" and e.get("agent") == "main"]
    assert answer_events[-1]["content"] == "收尾"
    tool_msg = client.chat.completions.create.call_args_list[1].kwargs["messages"][3]
    assert "工具参数解析失败" in tool_msg["content"]
    assert "file_writer" in tool_msg["content"]

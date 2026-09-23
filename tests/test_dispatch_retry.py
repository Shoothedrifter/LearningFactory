"""
tests/test_dispatch_retry.py
dispatch 子 Agent 调用撞 429（openai.RateLimitError）退避重试的 TDD 测试。
2026-09-21 实测（logs/afterfilewriter.txt）：并行 dispatch 启动瞬间并发请求
频繁撞速率限制（全程 15+ 次 429），主 Agent 只能消耗轮次逐个补派
（8 文件任务光补派耗 7 轮）。
"""

import json

import pytest

from helpers import make_rate_limit_error, make_tool_call, make_tool_calls_response, make_text_response

import agent


async def test_execute_dispatch_retries_once_on_rate_limit(monkeypatch):
    """普通版：首次撞 429 → 退避后重试一次成功。"""
    calls = {"n": 0}

    async def flaky_runner(task, prompt):
        calls["n"] += 1
        if calls["n"] == 1:
            raise make_rate_limit_error()
        return "重试后成功"

    monkeypatch.setitem(agent.SUBAGENT_RUNNERS, "file_writer", flaky_runner)
    monkeypatch.setattr(agent, "_DISPATCH_RETRY_DELAY_SECONDS", 0)  # 测试不等待

    result = await agent.execute_dispatch("file_writer", "写文件", {})
    assert result == "重试后成功"
    assert calls["n"] == 2


async def test_execute_dispatch_raises_after_retry_exhausted(monkeypatch):
    """普通版：重试用尽后 RateLimitError 照常上抛（交由既有 except 回填 [错误]）。"""
    calls = {"n": 0}

    async def always_limited(task, prompt):
        calls["n"] += 1
        raise make_rate_limit_error()

    monkeypatch.setitem(agent.SUBAGENT_RUNNERS, "file_writer", always_limited)
    monkeypatch.setattr(agent, "_DISPATCH_RETRY_DELAY_SECONDS", 0)

    with pytest.raises(Exception):
        await agent.execute_dispatch("file_writer", "写文件", {})
    assert calls["n"] == 2  # 初次 + 1 次重试，不多耗


async def test_execute_dispatch_no_retry_on_other_errors(monkeypatch):
    """普通版：非 429 异常不重试，直接上抛（守护性测试：避免掩盖真实缺陷）。"""
    calls = {"n": 0}

    async def broken_runner(task, prompt):
        calls["n"] += 1
        raise ValueError("子 Agent 崩溃")

    monkeypatch.setitem(agent.SUBAGENT_RUNNERS, "file_writer", broken_runner)

    with pytest.raises(ValueError):
        await agent.execute_dispatch("file_writer", "写文件", {})
    assert calls["n"] == 1


async def test_stream_dispatch_retries_once_on_rate_limit(patch_openai, monkeypatch):
    """流式版：子 Agent 事件流中途撞 429 → 退避后从头重跑，结果正常回填。"""
    calls = {"n": 0}

    def make_runner():
        async def runner(task: str, prompt: str):
            calls["n"] += 1
            yield json.dumps({"type": "status", "agent": "file_writer",
                              "message": "工作中"}, ensure_ascii=False)
            if calls["n"] == 1:
                raise make_rate_limit_error()
            yield json.dumps({"type": "answer", "agent": "file_writer",
                              "content": "file_writer 的结论"}, ensure_ascii=False)

        return runner

    monkeypatch.setattr(agent, "SUBAGENT_STREAM_RUNNERS", {"file_writer": make_runner()})
    monkeypatch.setattr(agent, "_DISPATCH_RETRY_DELAY_SECONDS", 0)
    client = patch_openai(
        make_tool_calls_response([
            make_tool_call("call_1", "dispatch_to_subagent",
                           agent_name="file_writer", task="写文件")
        ]),
        make_text_response("收尾"),
    )

    events = [json.loads(ev) async for ev in agent.run_main_agent_stream(
        system_prompt="测试", messages=[{"role": "user", "content": "写"}], sub_prompts={},
    )]

    assert calls["n"] == 2  # 第一次中途 429，重跑成功
    tool_msg = client.chat.completions.create.call_args_list[1].kwargs["messages"][3]
    assert "file_writer 的结论" in tool_msg["content"]

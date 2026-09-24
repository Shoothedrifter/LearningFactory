"""
tests/test_rate_limit_backoff.py
base.py 的 create 调用撞 429（openai.RateLimitError）指数退避重试的 TDD 测试。

2026-09-24 docker 实测（logs/docker_.txt）：dispatch 层固定 2 秒退避重试一次不足
以覆盖账户限流恢复窗口（15 次重试 12 次用尽），失败子 Agent 靠主 Agent 消耗轮次
补派，最终 12 轮耗尽靠用户手动「继续」收尾。

P1 修复的 base 层（治本位）：子 Agent 每轮的 create 撞 429 时原地按指数序列
（2/4/8 秒）重试同一调用，成功则当前轮继续——已执行的工具轮次零损失。对比
dispatch 层整跑重试（子 Agent 从头跑 10-40 轮），进度保留是关键差异。
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import RateLimitError

from helpers import make_rate_limit_error, make_text_response, make_tool_call, make_tool_calls_response

from learning_factory.agents import base


def _install_fake_tool(monkeypatch, counter: dict) -> None:
    """注册一个计数用的假工具，用于断言工具轮次是否被保留（而非从头重跑）。"""

    async def fake_echo(text: str) -> str:
        counter["n"] += 1
        return f"回显: {text}"

    monkeypatch.setitem(base.TOOL_REGISTRY, "fake_echo", fake_echo)


def _install_sleep_recorder(monkeypatch, sleeps: list) -> None:
    """替换 asyncio.sleep 为记录器：断言退避序列且测试零等待。"""

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)


def _make_client(side_effects) -> MagicMock:
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=side_effects)
    return client


async def test_create_backoff_preserves_progress_normal(monkeypatch):
    """普通版：主循环 create 撞 429×2 → 指数退避后原地重试成功，工具进度零损失。"""
    tool_runs = {"n": 0}
    sleeps: list[float] = []
    _install_fake_tool(monkeypatch, tool_runs)
    _install_sleep_recorder(monkeypatch, sleeps)

    # 轮 1 工具调用成功 → 轮 2 create 连撞 2 次 429 → 退避后重试成功返回文本
    client = _make_client([
        make_tool_calls_response([make_tool_call("call_1", "fake_echo", text="hi")]),
        make_rate_limit_error(),
        make_rate_limit_error(),
        make_text_response("最终答案"),
    ])
    monkeypatch.setattr(base, "_glm_client", client)

    result = await base.run_agent(
        system_prompt="测试", tool_schemas=[{"function": {"name": "fake_echo"}}],
        messages=[{"role": "user", "content": "跑"}],
        model="test-model", agent_name="tester", max_rounds=5,
    )

    assert result == "最终答案"
    assert client.chat.completions.create.call_count == 4  # 成功 2 次 + 429 两次
    assert tool_runs["n"] == 1  # 工具只执行一次：进度保留，未整跑重跑
    assert sleeps == [2.0, 4.0]  # 指数退避序列


async def test_create_backoff_preserves_progress_stream(monkeypatch):
    """流式版：主循环 create 撞 429×2 → 指数退避后重试成功，事件流完整。"""
    tool_runs = {"n": 0}
    sleeps: list[float] = []
    _install_fake_tool(monkeypatch, tool_runs)
    _install_sleep_recorder(monkeypatch, sleeps)

    client = _make_client([
        make_tool_calls_response([make_tool_call("call_1", "fake_echo", text="hi")]),
        make_rate_limit_error(),
        make_rate_limit_error(),
        make_text_response("最终答案"),
    ])
    monkeypatch.setattr(base, "_glm_client", client)

    events = [json.loads(ev) async for ev in base.run_agent_stream(
        system_prompt="测试", tool_schemas=[{"function": {"name": "fake_echo"}}],
        messages=[{"role": "user", "content": "跑"}],
        model="test-model", agent_name="tester", max_rounds=5,
    )]

    tool_events = [e for e in events if e["type"] == "tool_call"]
    calling_events = [e for e in tool_events if e.get("status") == "calling"]
    answers = [e for e in events if e["type"] == "answer"]
    # 工具调用不因 429 重试而重复（若整跑重跑会出现 2 个 calling 事件）
    assert len(calling_events) == 1
    assert answers and answers[-1]["content"] == "最终答案"
    assert client.chat.completions.create.call_count == 4
    assert tool_runs["n"] == 1
    assert sleeps == [2.0, 4.0]


async def test_create_raises_after_backoff_exhausted(monkeypatch):
    """退避用尽（1+3 次全 429）后 RateLimitError 照常冒泡，交上层兜底。"""
    sleeps: list[float] = []
    _install_sleep_recorder(monkeypatch, sleeps)

    client = _make_client([make_rate_limit_error()] * 4)
    monkeypatch.setattr(base, "_glm_client", client)

    with pytest.raises(RateLimitError):
        await base.run_agent(
            system_prompt="测试", tool_schemas=None,
            messages=[{"role": "user", "content": "跑"}],
            model="test-model", agent_name="tester", max_rounds=3,
        )

    assert client.chat.completions.create.call_count == 4  # 初次 + 3 次退避，不多耗
    assert sleeps == [2.0, 4.0, 8.0]


async def test_create_no_retry_on_other_errors(monkeypatch):
    """非 429 异常零重试直接冒泡（守护：不掩盖认证/网络等真实缺陷）。"""
    sleeps: list[float] = []
    _install_sleep_recorder(monkeypatch, sleeps)

    client = _make_client([ValueError("认证失败")])
    monkeypatch.setattr(base, "_glm_client", client)

    with pytest.raises(ValueError):
        await base.run_agent(
            system_prompt="测试", tool_schemas=None,
            messages=[{"role": "user", "content": "跑"}],
            model="test-model", agent_name="tester", max_rounds=3,
        )

    assert client.chat.completions.create.call_count == 1
    assert sleeps == []

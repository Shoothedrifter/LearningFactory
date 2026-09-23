"""
tests/test_subagent_event_dedup.py
子 Agent 重复事件去重的 TDD 测试。

背景：主 Agent 的流式调度层（agent.py 的 _run_tool_call_streaming）会为每个
dispatch 发一对 subagent start/done 事件；此前 agents/subagents.py 的流式
runner 也各自发一对，造成前端收到重复事件对。去重后：事件责任归调度层，
runner 只转发内部 run_agent_stream 的过程事件。
"""

import json

import agents.subagents as subagents_mod


async def test_stream_runners_do_not_emit_subagent_events(monkeypatch):
    """三个流式 runner 都不得再发 subagent start/done（事件由主 Agent 调度层统一发）。"""

    async def fake_run_agent_stream(**kwargs):
        # 模拟 run_agent_stream 的内部过程事件（status/tool_call/answer）
        for ev in (
            {"type": "status", "agent": kwargs["agent_name"], "message": "第 1 轮"},
            {"type": "tool_call", "agent": kwargs["agent_name"], "tool": "web_search", "status": "done"},
            {"type": "answer", "agent": kwargs["agent_name"], "content": f"{kwargs['agent_name']} 的结论"},
        ):
            yield json.dumps(ev, ensure_ascii=False)

    monkeypatch.setattr(subagents_mod, "run_agent_stream", fake_run_agent_stream)

    for runner in (
        subagents_mod.run_docs_researcher_stream,
        subagents_mod.run_repo_analyzer_stream,
        subagents_mod.run_web_researcher_stream,
    ):
        events = [json.loads(ev) async for ev in runner(task="研究 PyTorch", prompt="测试提示词")]

        # 不含任何 subagent 类型事件（去重：调度层是唯一来源）
        assert not [e for e in events if e["type"] == "subagent"], (
            f"{runner.__name__} 仍在发 subagent 事件"
        )
        # 内部过程事件被完整转发
        assert [e["type"] for e in events] == ["status", "tool_call", "answer"]

"""
tests/test_dispatch_semaphore.py
dispatch 并发节流的 TDD 测试。
2026-09-23 实测（logs/after_pytorch.txt）：同轮 8 个 file_writer dispatch 并发
启动，7/8 初次撞 429，固定退避重试因各路同步 sleep-重试而 11/11 全部用尽；
而单 dispatch 补派全部一次成功——限流是并发峰值型，需限制同时启动数。
"""

import asyncio
import json

from helpers import make_tool_call, make_tool_calls_response, make_text_response

import agent


async def test_dispatch_concurrency_capped(monkeypatch):
    """同轮并发 dispatch 的同时运行数被压到上限内，且全部完成。"""
    monkeypatch.setattr(agent, "_DISPATCH_CONCURRENCY_LIMIT", 2)
    running = {"now": 0, "peak": 0}

    async def slow_runner(task, prompt):
        running["now"] += 1
        running["peak"] = max(running["peak"], running["now"])
        await asyncio.sleep(0.02)  # 保证 5 个 dispatch 真正重叠
        running["now"] -= 1
        return f"完成 {task}"

    monkeypatch.setitem(agent.SUBAGENT_RUNNERS, "file_writer", slow_runner)

    results = await asyncio.gather(*(
        agent.execute_dispatch("file_writer", f"任务{i}", {}) for i in range(5)
    ))

    assert len(results) == 5          # 排队不丢任务
    assert running["peak"] <= 2       # 同时运行数被限在上限内


async def test_semaphore_default_limit_is_3():
    """默认并发上限 3（研究阶段三路并行 ALL THREE 的语义保持）。"""
    assert agent._DISPATCH_CONCURRENCY_LIMIT == 3


async def test_stream_dispatch_respects_semaphore(patch_openai, monkeypatch):
    """流式版 dispatch 同样受限流：limit=1 时两个子 Agent 串行（无重叠）。"""
    order = []

    def make_runner(name: str):
        async def runner(task: str, prompt: str):
            order.append(("start", name))
            await asyncio.sleep(0.01)
            order.append(("end", name))
            yield json.dumps({"type": "answer", "agent": name,
                              "content": f"{name} 完成"}, ensure_ascii=False)
        return runner

    monkeypatch.setattr(agent, "_DISPATCH_CONCURRENCY_LIMIT", 1)
    monkeypatch.setattr(agent, "SUBAGENT_STREAM_RUNNERS", {
        "docs_researcher": make_runner("docs"),
        "web_researcher": make_runner("web"),
    })
    client = patch_openai(
        make_tool_calls_response([
            make_tool_call("c1", "dispatch_to_subagent",
                           agent_name="docs_researcher", task="研究A"),
            make_tool_call("c2", "dispatch_to_subagent",
                           agent_name="web_researcher", task="研究B"),
        ]),
        make_text_response("收尾"),
    )

    events = [json.loads(ev) async for ev in agent.run_main_agent_stream(
        system_prompt="测试", messages=[{"role": "user", "content": "研究"}], sub_prompts={},
    )]

    # limit=1：不出现相邻两个 start（无重叠）；四个事件齐全（两个都跑完）
    assert len(order) == 4
    assert not any(order[i][0] == "start" and order[i + 1][0] == "start"
                   for i in range(len(order) - 1))
    # 两条 tool 结果都回填（dispatch 结果进对话历史）
    tool_msgs = client.chat.completions.create.call_args_list[1].kwargs["messages"][3:5]
    assert all("完成" in m["content"] for m in tool_msgs)

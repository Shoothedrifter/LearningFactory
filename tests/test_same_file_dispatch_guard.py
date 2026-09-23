"""
tests/test_same_file_dispatch_guard.py
同轮多 file_writer dispatch 指向同一文件的筛检防线 TDD 测试。
2026-09-21 实测（logs/afterfilewriter.txt :194-200）：主 Agent 违反
one-dispatch-per-file，对同一 learning-path.md 同轮发 Level 4/Level 5
两个 dispatch，叠加 429 失败补派导致全文顺序颠倒。
"""

import json
from pathlib import Path
from types import SimpleNamespace

from helpers import make_tool_call, make_tool_calls_response, make_text_response

import agent

TASK_L4 = "向已有文件 `Learning-Factory/learning-transformer/learning-path.md` 末尾追加 Level 4 内容"
TASK_L5 = "向已有文件 `Learning-Factory/learning-transformer/learning-path.md` 末尾追加 Level 5 内容"
TASK_README = "创建新文件 `Learning-Factory/learning-transformer/README2.md`，内容为导览"


def _fw_call(call_id: str, task: str):
    return make_tool_call(call_id, "dispatch_to_subagent",
                          agent_name="file_writer", task=task)


def test_same_file_dispatches_blocked():
    """两个 file_writer 任务指向同一文件：只放行第一个，第二个回填拦截串。"""
    blocked = agent._screen_same_file_dispatches([
        _fw_call("c1", TASK_L4), _fw_call("c2", TASK_L5), _fw_call("c3", TASK_README),
    ])
    assert set(blocked) == {1}  # 仅同文件的第二个被拦，不同文件的照常放行
    assert "同一文件" in blocked[1]


def test_guard_ignores_non_file_writer_dispatch():
    """研究型子 Agent 的 dispatch 不筛（无文件目标）。"""
    tcs = [
        make_tool_call("c1", "dispatch_to_subagent", agent_name="docs_researcher", task=TASK_L4),
        make_tool_call("c2", "dispatch_to_subagent", agent_name="web_researcher", task=TASK_L4),
    ]
    assert agent._screen_same_file_dispatches(tcs) == {}


def test_guard_passes_when_no_path_extractable():
    """task 提取不到路径时放行（宁放过勿错杀，防误伤无路径 task）。"""
    assert agent._screen_same_file_dispatches([
        _fw_call("c1", "写入学习路径文件的 Level 4"),  # 无反引号路径
        _fw_call("c2", "写入学习路径文件的 Level 5"),
    ]) == {}


def test_guard_ignores_malformed_args():
    """畸形 JSON 参数不在此拦截（走既有 MALFORMED_ARGS_MESSAGE 路径）。"""
    bad = SimpleNamespace(id="c1", function=SimpleNamespace(
        name="dispatch_to_subagent", arguments='{"agent_name": '))
    assert agent._screen_same_file_dispatches([bad]) == {}


async def test_plain_loop_blocks_second_same_file_dispatch(patch_openai, monkeypatch):
    """普通版集成：同文件双 dispatch 只执行第一个，第二个回填拦截文案。"""
    executed = []

    async def fake_runner(task, prompt):
        executed.append(task)
        return "已写入"

    monkeypatch.setitem(agent.SUBAGENT_RUNNERS, "file_writer", fake_runner)
    client = patch_openai(
        make_tool_calls_response([_fw_call("c1", TASK_L4), _fw_call("c2", TASK_L5)]),
        make_text_response("完成"),
    )

    await agent.run_main_agent(
        system_prompt="测试", messages=[{"role": "user", "content": "写"}], sub_prompts={},
    )

    assert executed == [TASK_L4]  # 第二个被拦，未执行
    tool_msgs = client.chat.completions.create.call_args_list[1].kwargs["messages"][3:5]
    assert tool_msgs[0]["content"] == "已写入"
    assert "同一文件" in tool_msgs[1]["content"]


async def test_stream_loop_blocks_second_same_file_dispatch(patch_openai, monkeypatch):
    """流式版集成：同文件双 dispatch 只执行第一个，第二个回填拦截文案。"""
    executed = []

    def make_runner():
        async def runner(task: str, prompt: str):
            executed.append(task)
            yield json.dumps({"type": "answer", "agent": "file_writer",
                              "content": "已写入"}, ensure_ascii=False)
        return runner

    monkeypatch.setattr(agent, "SUBAGENT_STREAM_RUNNERS", {"file_writer": make_runner()})
    client = patch_openai(
        make_tool_calls_response([_fw_call("c1", TASK_L4), _fw_call("c2", TASK_L5)]),
        make_text_response("完成"),
    )

    events = [json.loads(ev) async for ev in agent.run_main_agent_stream(
        system_prompt="测试", messages=[{"role": "user", "content": "写"}], sub_prompts={},
    )]

    assert executed == [TASK_L4]
    tool_msgs = client.chat.completions.create.call_args_list[1].kwargs["messages"][3:5]
    assert "同一文件" in tool_msgs[1]["content"]


# ── 锚定词形态（2026-09-23 实测 logs/after_pytorch.txt :218-224）──
# 第一轮 task 形态无反引号："文件路径: Learning-Factory/.../xxx.py 内容: ..."
# 原提取器只认反引号 token，对该形态失明（提取不到 → 放行）。


TASK_PLAIN = "文件路径: Learning-Factory/learning-pytorch/resources.md 内容: 追加六大常见陷阱"
TASK_PLAIN_OTHER = "文件路径: Learning-Factory/learning-pytorch/resources.md 内容: 追加视频教程表"


def test_extracts_path_from_anchor_form():
    """锚定词形态（无反引号）：文件路径: X 提取成功。"""
    got = agent._extract_dispatch_target_path(TASK_PLAIN)
    assert got == str(Path("Learning-Factory/learning-pytorch/resources.md").resolve())


def test_extracts_path_from_fullwidth_colon_anchor():
    """全角冒号变体（目标文件：X）同样提取成功。"""
    got = agent._extract_dispatch_target_path(
        "目标文件：Learning-Factory/learning-pytorch/resources.md\n请追加内容"
    )
    assert got == str(Path("Learning-Factory/learning-pytorch/resources.md").resolve())


def test_anchor_form_same_file_blocked():
    """集成：两个无反引号同文件 task——第二个被拦（本次修复的盲区）。"""
    blocked = agent._screen_same_file_dispatches([
        _fw_call("c1", TASK_PLAIN), _fw_call("c2", TASK_PLAIN_OTHER),
    ])
    assert set(blocked) == {1}
    assert "同一文件" in blocked[1]

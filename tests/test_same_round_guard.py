"""
tests/test_same_round_guard.py
同轮同文件并发写确定性拦截的 TDD 测试。

enforcement 只是提示词，模型可能违反（把同一文件的多个写入块放进同一轮）——
并发 open("a") 顺序未定义会导致内容静默颠倒。防线在 gather 之前静态筛检：
同一路径只放行第一次出现，其余回填拦截错误串。
"""

import json

from helpers import make_tool_call, make_tool_calls_response, make_text_response

from multi_agent import agent


async def test_same_round_same_file_second_blocked(patch_openai, tmp_path, monkeypatch):
    """普通版：同轮 write_file + append_file 同一文件——append 被拦，文件只含首块。"""
    monkeypatch.chdir(tmp_path)
    calls = [
        make_tool_call("c1", "write_file", path="out/doc.md", content="首块"),
        make_tool_call("c2", "append_file", path="out/doc.md", content="第二块"),
    ]
    client = patch_openai(
        make_tool_calls_response(calls),
        make_text_response("完成"),
    )

    answer = await agent.run_main_agent(
        system_prompt="测试", messages=[{"role": "user", "content": "写"}], sub_prompts={},
    )

    assert answer == "完成"
    msgs = client.chat.completions.create.call_args_list[1].kwargs["messages"]
    tool_msgs = [m for m in msgs if m["role"] == "tool"]
    assert "[成功]" in tool_msgs[0]["content"]      # write_file 放行执行
    assert "同一文件" in tool_msgs[1]["content"]     # append_file 被拦截
    assert (tmp_path / "out" / "doc.md").read_text(encoding="utf-8") == "首块"


async def test_same_round_different_files_allowed(patch_openai, tmp_path, monkeypatch):
    """普通版：同轮不同文件的写入不受影响（并行是合法的）。"""
    monkeypatch.chdir(tmp_path)
    calls = [
        make_tool_call("c1", "write_file", path="out/a.md", content="A"),
        make_tool_call("c2", "write_file", path="out/b.md", content="B"),
    ]
    client = patch_openai(
        make_tool_calls_response(calls),
        make_text_response("完成"),
    )

    answer = await agent.run_main_agent(
        system_prompt="测试", messages=[{"role": "user", "content": "写"}], sub_prompts={},
    )

    assert answer == "完成"
    assert (tmp_path / "out" / "a.md").read_text(encoding="utf-8") == "A"
    assert (tmp_path / "out" / "b.md").read_text(encoding="utf-8") == "B"
    msgs = client.chat.completions.create.call_args_list[1].kwargs["messages"]
    tool_msgs = [m for m in msgs if m["role"] == "tool"]
    assert all("[成功]" in m["content"] for m in tool_msgs)


async def test_stream_same_round_same_file_blocked(patch_openai, tmp_path, monkeypatch):
    """流式版：同轮同文件第二个调用被拦，事件流可见拦截结果，文件只含首块。"""
    monkeypatch.chdir(tmp_path)
    calls = [
        make_tool_call("c1", "write_file", path="out/doc.md", content="首块"),
        make_tool_call("c2", "append_file", path="out/doc.md", content="第二块"),
    ]
    patch_openai(
        make_tool_calls_response(calls),
        make_text_response("流式完成"),
    )

    events = [
        json.loads(ev)
        async for ev in agent.run_main_agent_stream(
            system_prompt="测试", messages=[{"role": "user", "content": "写"}], sub_prompts={},
        )
    ]

    answers = [e for e in events if e["type"] == "answer" and e.get("agent") == "main"]
    assert answers and answers[-1]["content"] == "流式完成"
    tool_events = [e for e in events if e["type"] == "tool_call"]
    blocked_events = [e for e in tool_events if "同一文件" in str(e.get("result", ""))]
    assert blocked_events, "拦截结果必须出现在事件流中"
    assert (tmp_path / "out" / "doc.md").read_text(encoding="utf-8") == "首块"

"""
tests/test_file_writer_wiring.py
P3 主 Agent 侧接线：file_writer 进 dispatch 枚举、主 Agent 移除直接写入工具、
enforcement 改为 dispatch 指示（1500 分块细则下沉到 prompts/file_writer.md）。
"""

from multi_agent import agent
from multi_agent.agents import subagents as subagents_mod


def _tool_names():
    return [t["function"]["name"] for t in agent.MAIN_AGENT_TOOLS]


def test_dispatch_enum_includes_file_writer():
    """enum 是实测有效的提示词通道：file_writer 必须在枚举里。"""
    enum = agent.DISPATCH_TOOL_SCHEMA["function"]["parameters"]["properties"]["agent_name"]["enum"]
    assert "file_writer" in enum


def test_dispatch_description_mentions_file_writer():
    """schema description 通道同步（实测部分有效）。"""
    assert "file_writer" in agent.DISPATCH_TOOL_SCHEMA["function"]["description"]


def test_main_agent_tools_exclude_direct_writes():
    """主 Agent 不再有直接写入工具（file_writer 垄断写入）。"""
    names = _tool_names()
    assert "write_file" not in names
    assert "append_file" not in names


def test_main_agent_tools_keep_inspection_tools():
    """主 Agent 保留 read_file/list_directory 用于查验产物。"""
    names = _tool_names()
    assert "read_file" in names
    assert "list_directory" in names


def test_enforcement_directs_file_writer():
    """enforcement Output Phase 改为 dispatch 指示；分块细则（1500）下沉。"""
    skills = agent.load_skills()
    assert "file_writer" in skills
    assert "NO file-writing tools" in skills
    assert "1500" not in skills


async def test_execute_dispatch_routes_file_writer(monkeypatch):
    """execute_dispatch 把 file_writer 路由到 run_file_writer。"""

    async def fake_run_file_writer(task, prompt):
        return f"已写入: {task} / {prompt}"

    # agent.py 经 from-import 持有 SUBAGENT_RUNNERS 的同一 dict 对象，setitem 生效
    monkeypatch.setitem(subagents_mod.SUBAGENT_RUNNERS, "file_writer", fake_run_file_writer)
    result = await agent.execute_dispatch(
        "file_writer", "写 learning-path.md", {"file_writer": "写入提示词"}
    )
    assert result == "已写入: 写 learning-path.md / 写入提示词"


def test_server_sub_prompts_include_file_writer():
    """server.py 的 SUB_PROMPTS 注册 file_writer（流式路径的提示词来源）。"""
    from multi_agent import server
    assert "file_writer" in server.SUB_PROMPTS
    assert server.SUB_PROMPTS["file_writer"]  # 非空（load_prompt 成功）


def test_malformed_args_message_directs_file_writer():
    """解析失败引导不得指向主 Agent 已移除的写入工具（P3 契约，终审 Issue 1）。"""
    assert "write_file" not in agent.MALFORMED_ARGS_MESSAGE
    assert "append_file" not in agent.MALFORMED_ARGS_MESSAGE
    assert "file_writer" in agent.MALFORMED_ARGS_MESSAGE


async def test_streaming_dispatch_routes_file_writer(patch_openai, monkeypatch):
    """流式链路：dispatch file_writer 经 _run_tool_call_streaming 路由到流式 runner。"""
    import json

    from helpers import make_tool_call, make_tool_calls_response, make_text_response

    async def fake_stream_runner(task: str, prompt: str):
        yield json.dumps({"type": "status", "agent": "file_writer", "message": "写入中"}, ensure_ascii=False)
        yield json.dumps({"type": "answer", "agent": "file_writer", "content": "已写入 8 块"}, ensure_ascii=False)

    monkeypatch.setattr(agent, "SUBAGENT_STREAM_RUNNERS", {"file_writer": fake_stream_runner})
    client = patch_openai(
        make_tool_calls_response([
            make_tool_call("c1", "dispatch_to_subagent", agent_name="file_writer", task="写 learning-path.md")
        ]),
        make_text_response("完成"),
    )

    events = [json.loads(ev) async for ev in agent.run_main_agent_stream(
        system_prompt="测试",
        messages=[{"role": "user", "content": "生成学习计划"}],
        sub_prompts={"file_writer": "写入提示词"},
    )]

    # file_writer 的 answer 被聚合回 tool 消息（进入第 2 次模型请求的 messages）
    tool_msgs = [
        m for m in client.chat.completions.create.call_args_list[1].kwargs["messages"]
        if m.get("role") == "tool"
    ]
    assert tool_msgs and "已写入 8 块" in tool_msgs[0]["content"]

"""
tests/test_cli_render.py
CLI 流式渲染纯函数：SSE 事件 → 终端行。
answer 主 Agent 事件由 main() 整段处理，render 返回 None。
"""

from learning_factory.agent import render_event


def test_subagent_start_line():
    line = render_event({"type": "subagent", "subagent": "docs_researcher",
                         "status": "start", "task": "查 PyTorch 官方文档的版本与核心概念" * 10})
    assert line is not None
    assert "docs_researcher" in line
    assert len(line) <= 80          # 任务摘要截断，单行不刷屏

def test_subagent_done_line():
    line = render_event({"type": "subagent", "subagent": "file_writer", "status": "done"})
    assert line is not None and "file_writer" in line

def test_subagent_start_task_newline_collapsed():
    """task 含换行/连续空白压成单空格，渲染结果仍是单行。"""
    line = render_event({"type": "subagent", "subagent": "docs_researcher",
                         "status": "start", "task": "查文档\n换行后半段"})
    assert line is not None
    assert "\n" not in line
    assert "查文档 换行后半段" in line

def test_subagent_unknown_status_renders_nothing():
    """status 为未知值（如 error）的 subagent 事件不渲染。

    防御未来新增状态被误渲染为「完成」；done 行仅在 status == done 时返回。
    """
    assert render_event({"type": "subagent", "subagent": "docs_researcher",
                         "status": "error"}) is None

def test_tool_call_line():
    line = render_event({"type": "tool_call", "agent": "main",
                         "tool": "web_search", "args": {"query": "asyncio semaphore"}})
    assert line is not None and "web_search" in line

def test_status_and_main_answer_render_nothing():
    """status 属噪音不渲染；main 的 answer 由调用方整段打印。"""
    assert render_event({"type": "status", "agent": "main", "message": "开始处理..."}) is None
    assert render_event({"type": "answer", "agent": "main", "content": "x"}) is None

def test_error_line():
    line = render_event({"type": "error", "message": "boom"})
    assert line is not None and "boom" in line


async def test_main_stream_renders_process_lines(patch_openai, monkeypatch, capsys):
    """main() 走流式版：子 Agent 过程行实时打印，答案整段输出。"""
    import json
    from learning_factory import agent
    from learning_factory.agents import base
    from helpers import make_tool_call, make_tool_calls_response, make_text_response

    # CI 无 .env / 真实 key：补假 key 过 ensure_api_key() 前置校验
    monkeypatch.setenv("GLM_API_KEY", "fake-key")
    monkeypatch.setattr(agent, "load_prompt", lambda f: "测试提示词")
    monkeypatch.setattr(agent, "load_skills", lambda: "")
    monkeypatch.setattr(agent, "new_session_path", lambda: __import__("pathlib").Path("/tmp/lf-test-session.jsonl"))
    inputs = iter(["查一下", "exit"])
    monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
    # dispatch file_writer → subagent start/done 事件 + 两轮文本收尾。
    # 响应队列实测 3 次（按调用时序）：
    #   1. 主 Agent 第 1 轮：tool_calls（dispatch file_writer）
    #   2. file_writer 子 Agent 第 1 轮：纯文本即收尾（run_file_writer_stream 真实执行）
    #   3. 主 Agent 第 2 轮：纯文本最终答案
    tc = make_tool_call("c1", "dispatch_to_subagent", agent_name="file_writer", task="写文件")
    client = patch_openai(
        make_tool_calls_response([tc]),
        make_text_response("研究完成"), make_text_response("最终答案"),
    )
    # base._get_client 的模块级 from-import 绑定不吃 patch_openai 的类替换，
    # 显式指到同一假 client，让 file_writer 的 create 与主 Agent 共用同一响应队列
    monkeypatch.setattr(base, "_glm_client", client)
    await agent.main()
    # mock 次数固化：主 Agent 2 次 + file_writer 1 次（实测值，防队列配置漂移）
    assert client.chat.completions.create.call_count == 3
    out = capsys.readouterr().out
    assert "▶ [file_writer] 写文件" in out   # 过程行已渲染
    assert "✔ [file_writer] 完成" in out
    assert "研究完成" not in out             # 子 Agent answer 聚合进工具结果，不渲染
    assert "最终答案" in out                 # main 的 answer 整段输出

"""
tests/test_file_writer_subagent.py
P3 子 Agent 写入引擎（file_writer）的 TDD 测试。
2026-09-19：主 Agent 移除直接写入工具后，file_writer 垄断长文档写入。
"""

import json
from pathlib import Path

from learning_factory import config
from learning_factory.agents import subagents as subagents_mod
from learning_factory.tools.filesystem import FILESYSTEM_TOOL_SCHEMAS


def test_file_writer_prompt_file_exists():
    """prompts/file_writer.md 存在且承载分块工作流与确定性摘要。"""
    prompt = Path("learning_factory/prompts/file_writer.md").read_text(encoding="utf-8").strip()
    assert prompt  # 非空
    assert "1400" in prompt  # 分块安全上限（低于工具 1500 硬限）
    assert "[成功]" in prompt  # 确定性摘要只认工具结果


async def test_run_file_writer_params(monkeypatch):
    """run_file_writer 以完整文件系统工具集、40 轮预算调用 run_agent。"""
    captured = {}

    async def fake_run_agent(**kwargs):
        captured.update(kwargs)
        return "写入完成"

    monkeypatch.setattr(subagents_mod, "run_agent", fake_run_agent)
    result = await subagents_mod.run_file_writer(task="写 learning-path.md", prompt="写入提示词")

    assert result == "写入完成"
    assert captured["system_prompt"] == "写入提示词"
    assert captured["tool_schemas"] == FILESYSTEM_TOOL_SCHEMAS
    assert captured["model"] == config.get_sub_agent_model()
    assert captured["max_rounds"] == 40  # 全文重写实测超 30 轮预算（2026-09-21）
    assert captured["agent_name"] == "file_writer"
    assert captured["messages"] == [{"role": "user", "content": "写 learning-path.md"}]


def test_file_writer_in_runner_tables():
    """两张调度表都注册 file_writer（dispatch 路由的依赖）。"""
    assert "file_writer" in subagents_mod.SUBAGENT_RUNNERS
    assert "file_writer" in subagents_mod.SUBAGENT_STREAM_RUNNERS


async def test_run_file_writer_stream_params(monkeypatch):
    """流式版与普通版参数一致（repo_analyzer_stream 同款先例）。"""
    captured = {}

    async def fake_run_agent_stream(**kwargs):
        captured.update(kwargs)
        yield json.dumps({"type": "answer", "agent": "file_writer", "content": "完成"})

    monkeypatch.setattr(subagents_mod, "run_agent_stream", fake_run_agent_stream)
    events = [ev async for ev in subagents_mod.run_file_writer_stream(task="写 README", prompt="写入提示词")]

    assert len(events) == 1
    assert captured["tool_schemas"] == FILESYSTEM_TOOL_SCHEMAS
    assert captured["max_rounds"] == 40  # 全文重写实测超 30 轮预算（2026-09-21）
    assert captured["agent_name"] == "file_writer"

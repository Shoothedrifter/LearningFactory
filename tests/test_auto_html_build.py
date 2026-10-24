"""
tests/test_auto_html_build.py
二期收尾钩子的 TDD 测试：本轮被写过的技术目录在对话轮结束时自动构建 HTML。

覆盖：命中构建 / 未触碰零噪音 / 非技术目录跳过 / 构建失败不炸钩子 /
输出根缺失静默 / render_event 渲染 / run_main_agent_stream 集成（事件次序）。
"""

import asyncio
import json
import os
import time
from pathlib import Path

from helpers import make_text_response

from learning_factory import agent


# ── 测试夹具 ────────────────────────────────────────────────────────────────

def _make_tech_dir(root: Path, name: str = "learning-x") -> Path:
    """造一个四产物齐全的技术目录。"""
    tech = root / name
    (tech / "code-examples").mkdir(parents=True)
    (tech / "README.md").write_text("# X\n\n简介", encoding="utf-8")
    (tech / "learning-path.md").write_text("## Level 1: 入门\n\n内容", encoding="utf-8")
    (tech / "resources.md").write_text("# 资源\n\n| 名称 | 链接 |\n|---|---|", encoding="utf-8")
    (tech / "code-examples" / "a.py").write_text("print(1)\n", encoding="utf-8")
    return tech


def _touch_future(path: Path, seconds: float = 300):
    """把目录内全部文件 mtime 拨到未来——预创建的目录也能命中"本轮被写过"。"""
    stamp = time.time() + seconds
    for p in path.rglob("*"):
        if p.is_file():
            os.utime(p, (stamp, stamp))


def _hook_events(since: float) -> list[dict]:
    """跑钩子生成器并解析为事件 dict 列表。"""
    return [json.loads(ev) for ev in agent._auto_html_build_events(since)]


# ── 钩子单元测试 ────────────────────────────────────────────────────────────

def test_hook_builds_touched_dir(tmp_path, monkeypatch):
    """本轮被写过（mtime 晚于 since）的技术目录 → 构建并产出 built 事件。"""
    root = tmp_path / "Factory"
    root.mkdir()
    tech = _make_tech_dir(root)
    monkeypatch.setenv("LEARNING_FACTORY_OUTPUT_DIR", str(root))

    events = _hook_events(since=time.time() - 60)

    assert len(events) == 1
    assert events[0]["type"] == "html_build"
    assert events[0]["status"] == "built"
    assert events[0]["path"].endswith("learning-x.html")
    assert Path(events[0]["path"]).exists()


def test_hook_skips_untouched_dir(tmp_path, monkeypatch):
    """未触碰（since 晚于全部 mtime）→ 零事件零噪音。"""
    root = tmp_path / "Factory"
    root.mkdir()
    _make_tech_dir(root)
    monkeypatch.setenv("LEARNING_FACTORY_OUTPUT_DIR", str(root))

    assert _hook_events(since=time.time() + 100) == []


def test_hook_skips_non_tech_dir(tmp_path, monkeypatch):
    """仅含 README.md 的目录不是技术目录（_is_tech_dir 收紧后的判定）→ 不构建。"""
    root = tmp_path / "Factory"
    root.mkdir()
    plain = root / "notes"
    plain.mkdir()
    (plain / "README.md").write_text("# 不是技术目录", encoding="utf-8")
    _touch_future(plain)
    monkeypatch.setenv("LEARNING_FACTORY_OUTPUT_DIR", str(root))

    assert _hook_events(since=time.time() - 60) == []


def test_hook_reports_build_failure_without_raising(tmp_path, monkeypatch):
    """构建失败（非 UTF-8 文件）→ 一条 failed 事件，生成器不抛异常。"""
    root = tmp_path / "Factory"
    root.mkdir()
    tech = _make_tech_dir(root)
    (tech / "code-examples" / "bad.bin").write_bytes(b"\x00\x05\x16\xb5")
    monkeypatch.setenv("LEARNING_FACTORY_OUTPUT_DIR", str(root))

    events = _hook_events(since=time.time() - 60)

    assert len(events) == 1
    assert events[0]["type"] == "html_build"
    assert events[0]["status"] == "failed"
    assert "bad.bin" in events[0]["message"]


def test_hook_missing_root_silent(tmp_path, monkeypatch):
    """输出根目录不存在 → 零事件零异常。"""
    monkeypatch.setenv("LEARNING_FACTORY_OUTPUT_DIR", str(tmp_path / "不存在"))

    assert _hook_events(since=time.time() - 60) == []


# ── render_event 渲染 ──────────────────────────────────────────────────────

def test_render_event_html_build():
    """html_build 事件渲染为终端一行：成功/失败两态。"""
    built = agent.render_event({
        "type": "html_build", "status": "built",
        "path": "Learning-Factory/learning-x/learning-x.html",
    })
    assert built == "[HTML] 已构建 Learning-Factory/learning-x/learning-x.html"

    failed = agent.render_event({
        "type": "html_build", "status": "failed",
        "path": "Learning-Factory/learning-x",
        "message": "文件读取失败（非 UTF-8）: xxx",
    })
    assert failed == "[HTML] 构建失败: 文件读取失败（非 UTF-8）: xxx"


# ── 流式集成：事件次序 ─────────────────────────────────────────────────────

def test_stream_emits_html_build_before_answer(tmp_path, monkeypatch, patch_openai):
    """自然结束路径：html_build 事件在 answer 事件之前 yield（answer 由
    main() 流结束后整段打印，钩子行先落地与过程行同屏次序一致）。"""
    root = tmp_path / "Factory"
    root.mkdir()
    _touch_future(_make_tech_dir(root))
    monkeypatch.setenv("LEARNING_FACTORY_OUTPUT_DIR", str(root))

    async def _collect():
        return [
            json.loads(ev)
            async for ev in agent.run_main_agent_stream(
                system_prompt="s", messages=[{"role": "user", "content": "hi"}],
                sub_prompts={},
            )
        ]

    patch_openai(make_text_response("最终答案"))
    events = asyncio.run(_collect())

    html_idx = [i for i, e in enumerate(events) if e["type"] == "html_build"]
    answer_idx = [i for i, e in enumerate(events) if e["type"] == "answer"]
    assert len(html_idx) == 1
    assert html_idx[0] < answer_idx[0]
    assert events[html_idx[0]]["status"] == "built"

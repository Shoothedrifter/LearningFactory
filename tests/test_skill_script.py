"""
tests/test_skill_script.py
skill 独立脚本 build_html.py 的 skill 形态专属行为：
pygments 可选降级、markdown 缺失报错可行动、PEP 723 内联依赖声明。

75 项既有行为断言随 test_html_builder.py / test_cli_build.py 迁移到
同一脚本（加载方式改为 helpers.load_build_html），不在此重复。
对应规格 docs/superpowers/specs/2026-10-30-skill-adaptation-design.md §6.4。
"""

import sys

from helpers import SCRIPT_PATH


def _kill_module(monkeypatch, *names):
    """把指定模块从 sys.modules 置 None，模拟其未安装（import 即 ImportError）。"""
    for name in names:
        monkeypatch.setitem(sys.modules, name, None)


def _make_tech_dir(tmp_path, name="learning-demo"):
    """构造最小可构建产物目录：README + 学习路径 + 代码示例。"""
    d = tmp_path / name
    d.mkdir()
    (d / "README.md").write_text("# 概览\n", encoding="utf-8")
    (d / "learning-path.md").write_text("## Level 1: 入门\n\n内容\n", encoding="utf-8")
    code = d / "code-examples"
    code.mkdir()
    (code / "hello.py").write_text("print('hi')\n", encoding="utf-8")
    return d


def test_degrades_without_pygments(monkeypatch, build_html_module_reload, tmp_path):
    """缺 pygments：模块可加载、HAS_PYGMENTS 为 False、构建成功且代码为纯 <pre>。

    对应 Review Focus #4：依赖缺失不得静默崩，功能完整视觉降级。
    """
    _kill_module(
        monkeypatch,
        "pygments", "pygments.lexers", "pygments.formatters",
        "pygments.formatters.html", "pygments.lexers.text",
    )
    mod = build_html_module_reload()
    assert mod.HAS_PYGMENTS is False

    d = _make_tech_dir(tmp_path)
    out = mod.build_html(d)
    text = out.read_text(encoding="utf-8")
    assert out.exists()
    assert "<pre" in text  # 代码示例以纯文本代码块呈现
    assert "print" in text  # 源码内容仍在


def test_missing_markdown_error_actionable(
    monkeypatch, build_html_module_reload, capsys, tmp_path
):
    """缺 markdown（硬依赖）：main 返回非 0，stderr 给出 pip install markdown 指引。

    对应 Review Focus #4：报错必须可行动。
    """
    _kill_module(monkeypatch, "markdown", "markdown.extensions")
    mod = build_html_module_reload()

    d = tmp_path / "learning-demo"
    d.mkdir()
    (d / "README.md").write_text("# x", encoding="utf-8")

    rc = mod.main([str(d)])
    err = capsys.readouterr().err
    assert rc != 0
    assert "pip install markdown" in err


def test_pep723_header_present():
    """脚本头部含 PEP 723 内联依赖声明，依赖列出 markdown 与 pygments。

    uv run 据此自动装依赖（spec §6.4），pygments 列出但代码内可选降级。
    """
    head = "\n".join(SCRIPT_PATH.read_text(encoding="utf-8").splitlines()[:30])
    assert "# /// script" in head
    assert "markdown" in head
    assert "pygments" in head

"""
tests/test_html_builder.py
学习产物单文件 HTML 构建器：收集、渲染、组装的纯函数测试。

对应规格 docs/superpowers/specs/2026-10-22-html-builder-design.md。
构建器零 LLM、零网络、输入目录只读；本文件钉住各纯函数行为。
"""

import pytest

from learning_factory.html_builder import (
    Artifacts,
    HtmlBuildError,
    collect_artifacts,
    highlight_css,
    render_markdown,
)


def test_collect_artifacts_all_present(tmp_path):
    """四类产物齐全时全部收集，字段为绝对存在的路径。"""
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    (tmp_path / "learning-path.md").write_text("x", encoding="utf-8")
    (tmp_path / "resources.md").write_text("x", encoding="utf-8")
    (tmp_path / "code-examples").mkdir()
    art = collect_artifacts(tmp_path)
    assert art.readme == tmp_path / "README.md"
    assert art.learning_path == tmp_path / "learning-path.md"
    assert art.resources == tmp_path / "resources.md"
    assert art.code_examples == tmp_path / "code-examples"


def test_collect_artifacts_missing_marked_none(tmp_path):
    """缺件降级：缺的产物字段为 None，不抛错。"""
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    art = collect_artifacts(tmp_path)
    assert art.readme is not None
    assert art.learning_path is None
    assert art.resources is None
    assert art.code_examples is None


def test_collect_artifacts_all_missing_raises(tmp_path):
    """四类产物全缺：明确报错（规格 §5）。"""
    with pytest.raises(HtmlBuildError, match="四类产物全缺"):
        collect_artifacts(tmp_path)


def test_artifacts_default_none():
    """Artifacts 默认全 None，供后续组装阶段直接使用。"""
    art = Artifacts()
    assert art.readme is None and art.learning_path is None
    assert art.resources is None and art.code_examples is None


def test_render_markdown_heading_and_bold():
    """基础块级渲染：标题与行内强调。"""
    html = render_markdown("# 标题\n\n**粗体**")
    assert "<h1" in html and "标题" in html
    assert "<strong>粗体</strong>" in html


def test_render_markdown_table():
    """resources.md 全是表格：tables 扩展必须生效。"""
    md = "| 资源 | 链接 |\n|------|------|\n| 官方 | https://example.com |"
    assert "<table>" in render_markdown(md)


def test_render_markdown_fenced_code_highlighted():
    """围栏代码块经 codehilite+Pygments 高亮（生成 span）。"""
    md = "```python\nprint('hi')\n```"
    html = render_markdown(md)
    assert 'class="highlight"' in html
    assert "<span" in html


def test_render_markdown_h2_gets_anchor_id():
    """toc 扩展为 h2 生成锚点 id（Level 进度条依赖）。"""
    html = render_markdown("## Level 1: 概览\n\n正文")
    assert '<h2 id="level-1">' in html


def test_highlight_css():
    """高亮主题 CSS 以 .highlight 为前缀，可整体注入模板。"""
    css = highlight_css()
    assert ".highlight" in css

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
    LevelInfo,
    collect_artifacts,
    extract_levels,
    highlight_css,
    render_markdown,
    render_progress,
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


def test_extract_levels_from_rendered_path():
    """从渲染后的学习路径提取 Level 编号、标题、锚点。"""
    md = "## Level 1: 概览与动机\n\n正文\n\n## Level 2: 安装\n\n正文\n"
    levels = extract_levels(render_markdown(md))
    assert [(lv.num, lv.title) for lv in levels] == [(1, "概览与动机"), (2, "安装")]
    assert levels[0].anchor == "level-1"


def test_extract_levels_empty_when_no_levels():
    """无 Level 标题的文档 → 空列表（降级：进度条隐藏）。"""
    assert extract_levels(render_markdown("# 无级别文档\n\n正文")) == []


def test_render_progress_marks():
    """进度条渲染：每个 Level 一个锚点步骤。"""
    html = render_progress([LevelInfo(1, "概览", "level-1"), LevelInfo(2, "安装", "level-2")])
    assert 'class="level-progress"' in html
    assert 'href="#level-1"' in html and 'href="#level-2"' in html
    assert "概览" in html and "安装" in html


def test_render_progress_empty_returns_empty_string():
    """空 Level 列表 → 空字符串（模板占位符直接替换为空）。"""
    assert render_progress([]) == ""

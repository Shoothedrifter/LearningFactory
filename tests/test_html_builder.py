"""
tests/test_html_builder.py
学习产物单文件 HTML 构建器：收集、渲染、组装的纯函数测试。

对应规格 docs/superpowers/specs/2026-10-22-html-builder-design.md。
构建器零 LLM、零网络、输入目录只读；本文件钉住各纯函数行为。
"""

import pytest

from learning_factory.html_builder import (
    Artifacts,
    CodeFile,
    CodeTree,
    HtmlBuildError,
    LevelInfo,
    build_code_tree,
    collect_artifacts,
    extract_levels,
    highlight_css,
    render_code_panel,
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


def _make_code_dir(tmp_path):
    code = tmp_path / "code-examples"
    return code


def test_build_code_tree_nested_and_highlighted(tmp_path):
    """嵌套目录收集：相对路径、语言识别、Pygments 高亮。"""
    code = _make_code_dir(tmp_path)
    (code / "01-hello").mkdir(parents=True)
    (code / "01-hello" / "a.yaml").write_text("apiVersion: v1\n", encoding="utf-8")
    tree = build_code_tree(code)
    assert len(tree.files) == 1
    assert tree.files[0].rel_path == "01-hello/a.yaml"
    assert tree.files[0].language == "yaml"
    assert 'class="highlight"' in tree.files[0].highlighted_html


def test_build_code_tree_unknown_suffix_plain_text(tmp_path):
    """未知扩展名回退纯文本，不告警不崩溃。"""
    code = _make_code_dir(tmp_path)
    code.mkdir()
    (code / "weird.conf").write_text("key=value\n", encoding="utf-8")
    tree = build_code_tree(code)
    assert tree.files[0].language == "text"
    assert tree.files[0].highlighted_html  # 纯文本也有输出


def test_build_code_tree_empty_dir(tmp_path):
    """空目录 → 空树（code tab 隐藏的判定依据）。"""
    code = _make_code_dir(tmp_path)
    code.mkdir()
    assert build_code_tree(code).files == []


def test_build_code_tree_only_empty_subdirs(tmp_path):
    """只有空子目录 → 同样视为无代码。"""
    code = _make_code_dir(tmp_path)
    (code / "01-empty").mkdir(parents=True)
    assert build_code_tree(code).files == []


def test_build_code_tree_non_utf8_raises_with_path(tmp_path):
    """非 UTF-8 代码文件：报错消息含文件路径（Review Focus #1）。"""
    code = _make_code_dir(tmp_path)
    code.mkdir()
    (code / "bad.py").write_bytes(b"\xff\xfe\x00not-utf8")
    with pytest.raises(HtmlBuildError, match="bad.py"):
        build_code_tree(code)


def test_render_code_panel_structure():
    """代码面板：文件树按钮 + 查看器，data-file 与面板 id 对应。"""
    tree = CodeTree(
        files=[
            CodeFile("01/a.yaml", "yaml", '<div class="highlight"><pre></pre></div>'),
            CodeFile("02/b.py", "python", '<div class="highlight"><pre></pre></div>'),
        ]
    )
    html = render_code_panel(tree)
    assert 'class="code-file-nav"' in html
    assert 'class="code-viewer"' in html
    assert 'data-file="cf0"' in html and 'id="cf0"' in html
    assert 'data-file="cf1"' in html and 'id="cf1"' in html
    assert "01/a.yaml" in html and "02/b.py" in html
    assert ">yaml<" in html and ">python<" in html  # 语言徽标


def test_render_code_panel_empty_tree():
    """空树 → 空字符串（占位符替换为空）。"""
    assert render_code_panel(CodeTree(files=[])) == ""

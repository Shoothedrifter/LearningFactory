"""
tests/test_html_builder.py
学习产物单文件 HTML 构建器：收集、渲染、组装的纯函数测试。

对应规格 docs/superpowers/specs/2026-10-22-html-builder-design.md。
构建器零 LLM、零网络、输入目录只读；本文件钉住各纯函数行为。
"""

import re

import pytest

from learning_factory.html_builder import (
    Artifacts,
    CodeFile,
    CodeTree,
    HtmlBuildError,
    LevelInfo,
    build_code_tree,
    build_html,
    collect_artifacts,
    extract_levels,
    highlight_css,
    load_template,
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


def test_build_code_tree_skips_dotfiles(tmp_path):
    """dotfile（.DS_Store 等隐藏系统文件）被跳过：不阻断构建也不进文件树（C1）。"""
    code = _make_code_dir(tmp_path)
    code.mkdir()
    # 真实 .DS_Store 二进制头（含非法 UTF-8 序列，macOS Finder 必然生成）
    (code / ".DS_Store").write_bytes(b"\x00\x05\x16\xb5\xb0\x21\x0f")
    (code / "a.py").write_text("print(1)\n", encoding="utf-8")
    (code / "sub").mkdir()
    (code / "sub" / ".hidden.py").write_text("x = 1\n", encoding="utf-8")
    tree = build_code_tree(code)
    assert [f.rel_path for f in tree.files] == ["a.py"]


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


def test_template_exists_and_holds_placeholders():
    """模板随包分发且占位符齐全（Task 6 的替换契约）。"""
    tpl = load_template()
    for ph in (
        "{{PAGE_TITLE}}", "{{NAV_HTML}}", "{{PANEL_OVERVIEW}}",
        "{{PANEL_LEARNING_PATH}}", "{{PANEL_RESOURCES}}", "{{PANEL_CODE}}",
        "{{PYGMENTS_CSS}}", "{{BUILD_META}}",
    ):
        assert ph in tpl


def test_template_offline_selfcontained_except_fonts():
    """自包含契约：唯一外链是 Google Fonts（Review Focus #5）。"""
    tpl = load_template()
    refs = re.findall(r'(?:src|href)="(https?://[^"]+)"', tpl)
    assert refs, "模板应至少包含字体 link"
    assert all(r.startswith("https://fonts.") for r in refs), refs


def test_template_accessibility_and_motion():
    """reduced-motion 支持 + hash 路由 + 外链新窗口（规格 §3.4/§3.6）。"""
    tpl = load_template()
    assert "prefers-reduced-motion" in tpl
    assert "#tab=" in tpl  # hash 路由
    # 模板经 JS 设置 target（a.target = '_blank'），断言钉住该行为而非具体空白写法
    assert re.search(r"""target\s*=\s*['"]_blank['"]""", tpl)


def _make_tech_dir(tmp_path, *, code=True, resources=True, readme=True, path=True):
    """构造一个技术产物目录 fixture（各产物可独立缺席）。"""
    d = tmp_path / "learning-demo"
    d.mkdir()
    if readme:
        (d / "README.md").write_text("# Demo 概览\n\n这是概览。", encoding="utf-8")
    if path:
        (d / "learning-path.md").write_text(
            "## Level 1: 入门\n\n内容一\n\n## Level 2: 进阶\n\n内容二\n",
            encoding="utf-8",
        )
    if resources:
        (d / "resources.md").write_text(
            "| 资源 | 链接 |\n|------|------|\n| 官方 | https://example.com |",
            encoding="utf-8",
        )
    if code:
        (d / "code-examples" / "01").mkdir(parents=True)
        (d / "code-examples" / "01" / "a.py").write_text("print(1)\n", encoding="utf-8")
    return d


def test_build_html_end_to_end(tmp_path):
    """四件齐全：输出到技术目录内，四个 tab 与进度条齐全，占位符全替换。"""
    d = _make_tech_dir(tmp_path)
    out = build_html(d)
    assert out == d / "learning-demo.html"
    html = out.read_text(encoding="utf-8")
    assert "demo · Learning Factory" in html  # 目录名去 learning- 前缀作标题
    for tab in ("overview", "path", "resources", "code"):
        assert f'data-tab="{tab}"' in html, tab
    assert 'class="level-progress"' in html
    assert "01/a.py" in html
    assert "{{" not in html  # 占位符一个不剩


def test_build_html_hides_missing_tabs(tmp_path):
    """缺件降级：缺席产物的 tab 不出现在导航（Review Focus #2）。"""
    d = _make_tech_dir(tmp_path, code=False, resources=False)
    html = build_html(d).read_text(encoding="utf-8")
    assert 'data-tab="code"' not in html
    assert 'data-tab="resources"' not in html
    assert 'data-tab="overview"' in html and 'data-tab="path"' in html


def test_build_html_empty_code_dir_hides_code_tab(tmp_path):
    """code-examples 存在但为空：tab 同样隐藏。"""
    d = _make_tech_dir(tmp_path, code=False)
    (d / "code-examples").mkdir()
    html = build_html(d).read_text(encoding="utf-8")
    assert 'data-tab="code"' not in html


def test_build_html_all_missing_raises(tmp_path):
    """全缺：collect 阶段即报错。"""
    d = tmp_path / "learning-empty"
    d.mkdir()
    with pytest.raises(HtmlBuildError, match="四类产物全缺"):
        build_html(d)


def test_build_html_non_utf8_markdown_raises_with_path(tmp_path):
    """非 UTF-8 的 md：报错含路径（Review Focus #1）。"""
    d = _make_tech_dir(tmp_path)
    (d / "README.md").write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(HtmlBuildError, match="README.md"):
        build_html(d)


def test_build_html_offline_no_external_refs_except_fonts(tmp_path):
    """离线契约：除 Google Fonts 外无任何外部引用（Review Focus #5）。"""
    html = build_html(_make_tech_dir(tmp_path)).read_text(encoding="utf-8")
    refs = re.findall(r'(?:src|href)="(https?://[^"]+)"', html)
    assert all(r.startswith("https://fonts.") for r in refs), refs


def test_build_html_without_levels_no_progress(tmp_path):
    """无 Level 标题：无进度条，页面其余部分正常（Review Focus #3）。"""
    d = _make_tech_dir(tmp_path)
    (d / "learning-path.md").write_text("# 没有级别的路径\n\n正文\n", encoding="utf-8")
    html = build_html(d).read_text(encoding="utf-8")
    assert 'class="level-progress"' not in html
    assert 'data-tab="path"' in html


def test_build_html_output_override(tmp_path):
    """--output 覆盖输出路径。"""
    d = _make_tech_dir(tmp_path)
    custom = tmp_path / "out" / "custom.html"
    custom.parent.mkdir()
    out = build_html(d, output=custom)
    assert out == custom and custom.exists()


def test_build_html_input_dir_untouched(tmp_path):
    """输入目录只读：构建后产物文件内容不变（Global Constraints）。"""
    d = _make_tech_dir(tmp_path)
    before = {
        p.relative_to(d).as_posix(): p.read_bytes()
        for p in d.rglob("*") if p.is_file()
    }
    build_html(d)
    after = {
        p.relative_to(d).as_posix(): p.read_bytes()
        for p in d.rglob("*") if p.is_file() and p.name != "learning-demo.html"
    }
    assert before == after


def test_build_html_warns_missing_artifacts_to_stderr(tmp_path, capsys):
    """缺件降级向 stderr 打警告：含目录名与缺件名（I1 / 规格 §5）。"""
    d = _make_tech_dir(tmp_path, code=False, resources=False)
    build_html(d)
    err = capsys.readouterr().err
    assert "learning-demo" in err
    assert "resources.md" in err and "code-examples" in err


def test_build_html_warns_empty_code_dir(tmp_path, capsys):
    """code-examples 存在但为空目录：同样警告（tab 隐藏须可见，I1）。"""
    d = _make_tech_dir(tmp_path, code=False)
    (d / "code-examples").mkdir()
    build_html(d)
    err = capsys.readouterr().err
    assert "learning-demo" in err and "code-examples" in err


def test_build_html_read_error_oserror_wrapped(tmp_path):
    """README.md 实为目录（OSError 家族）：包装为含路径的 HtmlBuildError（I2）。"""
    d = _make_tech_dir(tmp_path)
    (d / "README.md").unlink()
    (d / "README.md").mkdir()
    with pytest.raises(HtmlBuildError, match="README.md"):
        build_html(d)


def test_build_html_output_missing_parent_raises_with_path(tmp_path):
    """输出路径父目录不存在：HtmlBuildError 含输出路径（I2）。"""
    d = _make_tech_dir(tmp_path)
    with pytest.raises(HtmlBuildError, match="nope"):
        build_html(d, output=tmp_path / "nope" / "x.html")


def test_build_html_literal_placeholder_in_content_preserved(tmp_path):
    """用户内容中的字面占位符不被二次替换（单 pass，I4）。

    模板引擎类技术（Jinja2/Vue 等）的学习产物正文含 {{...}} 是常态，
    链式 replace 会把整段 CSS/面板注入用户内容。
    """
    d = _make_tech_dir(tmp_path)
    (d / "README.md").write_text(
        "# 模板示例\n\nJinja2 语法演示：`{{PYGMENTS_CSS}}` 应保持字面。", encoding="utf-8"
    )
    html = build_html(d).read_text(encoding="utf-8")
    # 用户正文中的字面占位符保持原样，且位于 body（style 块之后）
    assert "{{PYGMENTS_CSS}}" in html
    assert html.index("{{PYGMENTS_CSS}}") > html.index("</style>")
    # 真正的 Pygments CSS 仍注入且只在 head 的 style 位置出现一次
    assert html.count("line-height: 125%") == 1
    assert html.index("line-height: 125%") < html.index("</style>")


def test_build_html_escapes_tech_name_in_title(tmp_path):
    """目录名含 HTML 特殊字符（&<）：标题注入前转义（M2）。"""
    d = tmp_path / "learning-a&b<c"
    d.mkdir()
    (d / "README.md").write_text("# x", encoding="utf-8")
    html = build_html(d).read_text(encoding="utf-8")
    assert "<title>a&amp;b&lt;c · Learning Factory</title>" in html

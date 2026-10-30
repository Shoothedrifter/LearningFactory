"""
tests/test_html_builder.py
学习产物单文件 HTML 构建器：收集、渲染、组装的纯函数测试。

对应规格 docs/superpowers/specs/2026-10-22-html-builder-design.md。
构建器零 LLM、零网络、输入目录只读；本文件钉住各纯函数行为。

2026-10-31 起被测对象迁移为 skill 独立脚本
.agents/skills/learning-factory/scripts/build_html.py（原
learning_factory/html_builder.py 冻结保留），符号经文件位置加载解包，
断言一律不变（迁移记录见 2026-10-30-skill-adaptation-design.md J9）。
"""

import re

import pytest

from helpers import load_build_html

_bh = load_build_html()
Artifacts = _bh.Artifacts
CodeFile = _bh.CodeFile
CodeTree = _bh.CodeTree
HtmlBuildError = _bh.HtmlBuildError
LevelInfo = _bh.LevelInfo
build_code_tree = _bh.build_code_tree
build_html = _bh.build_html
collect_artifacts = _bh.collect_artifacts
extract_levels = _bh.extract_levels
highlight_css = _bh.highlight_css
load_template = _bh.load_template
render_code_panel = _bh.render_code_panel
render_markdown = _bh.render_markdown
render_progress = _bh.render_progress


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


def test_render_markdown_autolinks_bare_url():
    """裸 URL 自动链接：列表项冒号后的 URL 变可点击 <a>（resources.md 主形态）。"""
    html = render_markdown("- **官方文档**: https://example.com/docs/index")
    assert '<a href="https://example.com/docs/index">' in html


def test_render_markdown_autolinks_url_in_table_cell():
    """表格单元格内的裸 URL 同样可点击（表格形态的 resources.md）。"""
    md = "| 资源 | 链接 |\n|------|------|\n| 官方 | https://example.com |"
    assert '<a href="https://example.com">' in render_markdown(md)


def test_render_markdown_autolink_skips_inline_and_fenced_code():
    """行内代码与围栏代码块内的 URL 保持纯文本（代码不链接化）。"""
    inline = render_markdown("安装 `pip install https://example.com/x` 见上")
    assert "<a href" not in inline
    fenced = render_markdown("```bash\npip install https://example.com/x\n```")
    assert "<a href" not in fenced


def test_render_markdown_autolink_leaves_markdown_links_alone():
    """已是 [text](url) 的链接不双重处理：该 href 只渲染一个 <a>，裸 URL 照常链接。"""
    html = render_markdown("[文档](https://example.com/docs) 与裸 https://example.com")
    assert html.count('href="https://example.com/docs"') == 1
    assert '<a href="https://example.com">' in html


def test_render_markdown_autolink_trims_trailing_punctuation():
    """URL 尾随中英文标点不进 href：句号、句点、逗号在链接边界剥掉。"""
    html = render_markdown("详见 https://example.com/page。以及 https://example.com/a,")
    assert '<a href="https://example.com/page">' in html
    assert '<a href="https://example.com/a">' in html


def test_render_markdown_autolink_trims_unbalanced_paren():
    """括号文本内的裸 URL：ASCII 孤立尾 ) 剥离（括号平衡），全角 ）直接终止。"""
    html = render_markdown("参见 (见 https://example.com/a) 与（https://example.com/b）")
    assert '<a href="https://example.com/a">' in html
    assert '<a href="https://example.com/b">' in html


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


def test_render_code_panel_nested_dir_details(tmp_path):
    """目录嵌套：子目录渲染为默认展开的 details，文件按钮嵌在直属目录层。

    规格 §3.2 左侧文件树（目录嵌套）：目录用原生 <details open>（无 JS
    可展开收起、可访问性原生），按钮只显示文件名，title 悬停给完整路径。
    """
    code = _make_code_dir(tmp_path)
    code.mkdir()
    (code / "utils").mkdir()
    (code / "utils" / "helper.py").write_text("x = 1\n", encoding="utf-8")
    (code / "top.py").write_text("print(1)\n", encoding="utf-8")
    html = render_code_panel(build_code_tree(code))
    # utils 目录：details 默认展开、summary 为目录名
    m = re.search(
        r'<details class="code-dir" open>\s*<summary>.*?utils.*?</summary>(.*?)</details>',
        html, re.S,
    )
    assert m, "utils 目录应渲染为默认展开的 details"
    # utils 下的文件按钮嵌套在 details 内；文件名作按钮文本、全路径进 title
    assert 'data-file="cf1"' in m.group(1)
    assert ">helper.py<" in m.group(1)
    assert 'title="utils/helper.py"' in m.group(1)
    # 排序在前的顶层文件 top.py（cf0）出现在第一个 details 之前（顶层按钮）
    assert html.index('data-file="cf0"') < html.index("<details")
    assert 'title="top.py"' in html
    # data-file ↔ viewer id 契约在嵌套结构下保持
    assert 'id="cf0"' in html and 'id="cf1"' in html


def test_render_code_panel_flat_files_no_details(tmp_path):
    """平铺目录（所有文件在根层）：不得多出无意义的 details 包裹。"""
    code = _make_code_dir(tmp_path)
    code.mkdir()
    (code / "a.py").write_text("a = 1\n", encoding="utf-8")
    (code / "b.yaml").write_text("k: v\n", encoding="utf-8")
    html = render_code_panel(build_code_tree(code))
    assert "<details" not in html
    assert "<summary" not in html
    assert 'data-file="cf0"' in html and 'data-file="cf1"' in html
    assert 'class="code-file-nav"' in html


def test_render_code_panel_multilevel_dirs(tmp_path):
    """多层嵌套：a/b/f.py 渲染为 details a > details b > 文件按钮。"""
    code = _make_code_dir(tmp_path)
    (code / "a" / "b").mkdir(parents=True)
    (code / "a" / "b" / "f.py").write_text("f = 1\n", encoding="utf-8")
    (code / "a" / "g.py").write_text("g = 1\n", encoding="utf-8")
    html = render_code_panel(build_code_tree(code))
    assert html.count("<details") == 2  # 两层目录各一个 details
    # 外层 summary（a）的子容器内紧跟内层目录的 details（深度优先展开）
    assert re.search(r"</summary>\s*<div class=\"dir-children\">\s*<details", html), \
        "内层目录 details 应嵌套在外层目录的子容器开头"
    # 排序（a/b/f.py < a/g.py）：cf0 为深层文件、cf1 为 a 直属文件
    assert 'title="a/b/f.py"' in html and 'title="a/g.py"' in html
    assert 'id="cf0"' in html and 'id="cf1"' in html


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


def test_template_nojs_fallback_and_motion_gating():
    """无 JS 后备（M1）+ 标签过渡/平滑滚动的动效门控（规格 §3.4）。"""
    tpl = load_template()
    # M1：panel 隐藏仅在 JS 生效时应用（.js 前缀由 JS 首行添加），
    # 禁 JS 时四个面板纵向全显、锚点可用（兑现无 JS 后备承诺）
    assert ".js .panel" in tpl
    assert "document.body.classList.add('js')" in tpl
    assert "\n.panel { display: none" not in tpl  # 裸隐藏规则已移除
    # 门控：side-tab 的 transition 与 hover 位移只在 no-preference 下启用
    base = re.search(r"\.side-tab \{[^}]*\}", tpl).group(0)
    assert "transition" not in base  # 基础规则不再携带动画
    gate = re.search(
        r"@media \(prefers-reduced-motion: no-preference\) \{\n  \.side-tab \{[^}]*\}",
        tpl,
    )
    assert gate and "transition" in gate.group(0)
    # 门控：平滑滚动经 matchMedia 条件化为 auto/smooth
    assert "matchMedia('(prefers-reduced-motion: reduce)')" in tpl
    assert re.search(r"behavior:\s*reduceMotion \? 'auto' : 'smooth'", tpl)


def test_template_tree_details_css():
    """文件树 details/summary 样式：层级缩进 + 动效门控的展开过渡（I5）。"""
    tpl = load_template()
    for sel in (".code-dir", ".dir-children", ".dir-arrow", "summary"):
        assert sel in tpl, sel
    # 展开过渡（箭头旋转 + 内容淡入位移）只在 no-preference 下启用
    assert "tree-fade" in tpl  # 内容淡入位移动画的 keyframes
    base_arrow = re.search(r"\.dir-arrow \{[^}]*\}", tpl).group(0)
    assert "transition" not in base_arrow  # 基础规则不携带动画
    gate = re.search(
        r"@media \(prefers-reduced-motion: no-preference\) \{\n  \.dir-arrow \{[^}]*\}",
        tpl,
    )
    assert gate and "transition" in gate.group(0)


def test_template_scrollspy_js_and_css():
    """scroll spy：IntersectionObserver 高亮视口内 Level + active 视觉态（I5）。"""
    tpl = load_template()
    assert "IntersectionObserver" in tpl
    # 注册前检查：无进度条（无 Level）或浏览器不支持时静默跳过
    assert "'IntersectionObserver' in window" in tpl
    # CSS 视觉态：当前步骤高亮（薰衣草加深，与 Notebook Tabs 色板一致）
    assert ".progress-step.active" in tpl


def test_template_js_viewer_exclusive_display():
    """JS 生效时查看器互斥显示（浏览器实测发现的存量缺陷，I5 自审修复）。

    .code-viewer:first-of-type 恒 display:block：点击非首文件按钮时
    首文件查看器与目标查看器同屏叠显。first-of-type 兜底只应服务无 JS
    环境；JS 场景由 .active 独占（启动时已给首按钮加 active，默认首文件
    语义不变）。
    """
    tpl = load_template()
    assert ".js .code-viewer { display: none" in tpl
    assert ".js .code-viewer.active { display: block" in tpl
    # JS 启动时给首按钮对应查看器补 active（否则初始面板空白）
    assert re.search(r"firstView\.classList\.add\('active'\)", tpl)


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
    """离线契约：除 Google Fonts 外无任何外部资源引用（Review Focus #5）。

    只约束会加载资源的标签（link/script/img 等）；正文 <a href> 是跳转
    链接（裸 URL 自动链接产生），不触发网络加载，不在契约内。
    """
    html = build_html(_make_tech_dir(tmp_path)).read_text(encoding="utf-8")
    refs = [
        url
        for tag, url in re.findall(r'<(\w+)[^>]*?(?:src|href)="(https?://[^"]+)"', html)
        if tag != "a"
    ]
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

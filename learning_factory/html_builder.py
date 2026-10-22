"""
html_builder.py
学习产物单文件 HTML 构建器：把单个技术目录（README.md / learning-path.md /
resources.md / code-examples/）聚合为一个 Notebook Tabs 风格的自包含 HTML。

设计约束（见规格 2026-10-22-html-builder-design.md）：
- 纯函数渲染，零 LLM、零网络；输入目录只读
- 产物 HTML 除 Google Fonts 外零外部引用
"""

import argparse
import html as _html
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import markdown
from pygments import highlight as _pyg_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name


# 构建器版本号（产物页脚标注用；未安装场景回退 unknown）
try:
    from importlib.metadata import PackageNotFoundError, version as _pkg_version

    _VERSION = _pkg_version("learning-factory")
except PackageNotFoundError:
    _VERSION = "unknown"


class HtmlBuildError(Exception):
    """构建失败：消息面向用户，尽量包含文件路径。"""


# 四类产物的固定文件名（CLI 判定技术目录也依赖此清单）
ARTIFACT_NAMES: tuple[str, ...] = (
    "README.md",
    "learning-path.md",
    "resources.md",
    "code-examples",
)


@dataclass(frozen=True)
class Artifacts:
    """单个技术目录的产物收集结果；缺件为 None（降级隐藏对应 tab）。"""

    readme: Path | None = None
    learning_path: Path | None = None
    resources: Path | None = None
    code_examples: Path | None = None


def collect_artifacts(directory: Path) -> Artifacts:
    """收集目录内的四类产物；存在的记路径，缺的记 None。

    四类全缺时抛 HtmlBuildError（规格 §5：全缺报错退出）。
    """
    directory = Path(directory)
    found = Artifacts(
        readme=directory / "README.md" if (directory / "README.md").exists() else None,
        learning_path=(
            directory / "learning-path.md"
            if (directory / "learning-path.md").exists()
            else None
        ),
        resources=(
            directory / "resources.md" if (directory / "resources.md").exists() else None
        ),
        code_examples=(
            directory / "code-examples"
            if (directory / "code-examples").is_dir()
            else None
        ),
    )
    if all(
        v is None
        for v in (found.readme, found.learning_path, found.resources, found.code_examples)
    ):
        raise HtmlBuildError(f"四类产物全缺，无法构建：{directory}")
    return found


# markdown 渲染配置：表格（resources.md）、围栏代码（学习路径内代码块）、
# toc（标题锚点，进度条跳转依赖）、codehilite（Pygments 高亮）
_MD_EXTENSIONS = ["tables", "fenced_code", "toc", "codehilite"]
_MD_CONFIG = {"codehilite": {"css_class": "highlight", "guess_lang": False}}


def render_markdown(text: str) -> str:
    """markdown 文本 → HTML 片段。"""
    return markdown.markdown(text, extensions=_MD_EXTENSIONS, extension_configs=_MD_CONFIG)


def highlight_css() -> str:
    """Pygments friendly 主题（浅色，适配奶油纸面）的 .highlight 样式。"""
    return HtmlFormatter(style="friendly").get_style_defs(".highlight")


# 匹配渲染后学习路径的 Level 标题：<h2 id="level-1">Level 1: 概览与动机</h2>
# （中文部分被 toc 默认 slugify 丢弃，id 恒为 level-N，见规格 §3.2）
_H2_LEVEL_RE = re.compile(r'<h2 id="([^"]+)">\s*Level\s*(\d+)\s*[:：]\s*(.+?)</h2>')


@dataclass(frozen=True)
class LevelInfo:
    """学习路径的一个级别（进度条的一个步骤）。"""

    num: int
    title: str
    anchor: str


def extract_levels(rendered_html: str) -> list[LevelInfo]:
    """从渲染后的 learning-path HTML 提取 Level 列表；无则空列表。"""
    levels = []
    for anchor, num, title in _H2_LEVEL_RE.findall(rendered_html):
        clean = re.sub(r"<[^>]+>", "", title).strip()
        levels.append(LevelInfo(num=int(num), title=clean, anchor=anchor))
    return levels


def render_progress(levels: list[LevelInfo]) -> str:
    """Level 横向进度条 HTML；无级别返回空字符串。

    锚点跳转由模板 JS 接管（先切到学习路径 tab 再平滑滚动），
    href 仅作无 JS 环境的后备。
    """
    if not levels:
        return ""
    steps = "".join(
        f'<a class="progress-step" href="#{lv.anchor}">'
        f'<span class="step-num">{lv.num:02d}</span>'
        f'<span class="step-title">{lv.title}</span></a>'
        for lv in levels
    )
    return f'<nav class="level-progress" aria-label="学习进度">{steps}</nav>'


# 扩展名 → Pygments 语言名（规格 §4.4）；未列出的扩展名回退纯文本
_LANG_BY_SUFFIX: dict[str, str] = {
    ".yaml": "yaml", ".yml": "yaml",
    ".py": "python",
    ".sh": "bash", ".bash": "bash",
    ".js": "javascript", ".ts": "typescript",
    ".json": "json",
    ".md": "markdown",
    ".go": "go", ".rs": "rust",
    ".sql": "sql", ".toml": "toml",
    ".txt": "text", ".tf": "hcl",
}


@dataclass(frozen=True)
class CodeFile:
    """一个代码示例文件：相对路径、语言名、预高亮 HTML。"""

    rel_path: str
    language: str
    highlighted_html: str


@dataclass(frozen=True)
class CodeTree:
    """code-examples/ 的收集结果；空目录 → files=[]。"""

    files: list[CodeFile]


def build_code_tree(code_dir: Path) -> CodeTree:
    """遍历代码示例目录：按相对路径排序，全部预高亮嵌入。

    跳过任一路径段以 . 开头的隐藏文件（.DS_Store 等 macOS 系统垃圾，
    与 git/rsync 的默认忽略惯例一致，避免其阻断构建或混入产物）。
    非 UTF-8 / 不可读文件抛 HtmlBuildError（消息含路径，规格 §5）。
    """
    code_dir = Path(code_dir)
    files: list[CodeFile] = []
    for path in sorted(code_dir.rglob("*")):
        if not path.is_file():
            continue
        if any(part.startswith(".") for part in path.relative_to(code_dir).parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise HtmlBuildError(f"文件读取失败（非 UTF-8）: {path}") from exc
        except OSError as exc:
            raise HtmlBuildError(f"文件读取失败: {path}（{exc.strerror or exc}）") from exc
        language = _LANG_BY_SUFFIX.get(path.suffix.lower(), "text")
        lexer = get_lexer_by_name(language) if language != "text" else TextLexer()
        highlighted = _pyg_highlight(
            text, lexer, HtmlFormatter(linenos="table", cssclass="highlight")
        )
        files.append(
            CodeFile(
                rel_path=path.relative_to(code_dir).as_posix(),
                language=language,
                highlighted_html=highlighted,
            )
        )
    return CodeTree(files=files)


def _render_tree_button(idx: int, f: CodeFile) -> str:
    """文件树按钮：文本只显示文件名（目录名由所在层级体现），
    title 悬停提示完整相对路径（同名文件跨目录时的辨别线索）。"""
    name = f.rel_path.rsplit("/", 1)[-1]
    return (
        f'<button class="code-file-btn" data-file="cf{idx}"'
        f' title="{_html.escape(f.rel_path)}">'
        f"{_html.escape(name)}<i class=\"lang-chip\">{f.language}</i></button>"
    )


def _render_tree_level(items: list[tuple[int, CodeFile]], depth: int) -> str:
    """递归渲染文件树的一层：直属文件为按钮，子目录为原生 details。

    - 保持 build_code_tree 的排序顺序输出（按钮与目录的相对次序稳定，
      与 viewer 的 cfN 编号观感一致）
    - 目录默认 open（信息量与平铺一致，可手动收起；无 JS 亦可开合）
    """
    parts: list[str] = []
    seen_dirs: set[str] = set()
    for idx, f in items:
        segs = f.rel_path.split("/")
        if len(segs) == depth + 1:
            parts.append(_render_tree_button(idx, f))
            continue
        dir_name = segs[depth]
        if dir_name in seen_dirs:
            continue
        seen_dirs.add(dir_name)
        # 同名前缀子树：收集该目录下全部文件递归渲染（文件数小，线性过滤足够）
        sub = [(i, g) for i, g in items if g.rel_path.split("/")[depth] == dir_name]
        parts.append(
            f'<details class="code-dir" open>'
            f'<summary><i class="dir-arrow" aria-hidden="true"></i>'
            f"{_html.escape(dir_name)}</summary>"
            f'<div class="dir-children">{_render_tree_level(sub, depth + 1)}</div>'
            f"</details>"
        )
    return "".join(parts)


def render_code_panel(tree: CodeTree) -> str:
    """代码 tab 面板：左侧文件树（目录嵌套，规格 §3.2）+ 右侧查看器（默认首文件）。

    data-file="cfN" 与右侧 id="cfN" 一一对应（两侧同源枚举，嵌套不破坏契约）；
    无子目录的平铺树不输出任何 details 包裹。
    """
    if not tree.files:
        return ""
    nav = _render_tree_level(list(enumerate(tree.files)), depth=0)
    viewers = "".join(
        f'<div class="code-viewer" id="cf{i}">{f.highlighted_html}</div>'
        for i, f in enumerate(tree.files)
    )
    return (
        f'<div class="code-layout"><nav class="code-file-nav">{nav}</nav>'
        f'<div class="code-views">{viewers}</div></div>'
    )


# 模板随包分发（pyproject package-data 打包，见 Task 8），按包内路径读取
TEMPLATE_PATH = Path(__file__).parent / "templates" / "learning_page.html"


def load_template() -> str:
    """读取页面骨架模板（cwd 无关）。"""
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def _read_utf8(path: Path) -> str:
    """读 UTF-8 文件；失败时抛含路径的 HtmlBuildError。

    OSError 家族（权限不足、路径实为目录等）同样包装，
    批量模式下单个目录读取失败不至于裸抛 traceback 中断其余目录。
    """
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise HtmlBuildError(f"文件读取失败（非 UTF-8）: {path}") from exc
    except OSError as exc:
        raise HtmlBuildError(f"文件读取失败: {path}（{exc.strerror or exc}）") from exc


# tab 定义：(data-tab 键, 中文标签, 对应 Artifacts 字段名)；code 的显隐另判
_TABS: tuple[tuple[str, str, str], ...] = (
    ("overview", "概览", "readme"),
    ("path", "学习路径", "learning_path"),
    ("resources", "资源", "resources"),
)


def _render_nav(art: Artifacts, show_code: bool) -> str:
    """右缘竖排标签：仅渲染存在的产物（规格 §5 缺件降级）。"""
    buttons = "".join(
        f'<button class="side-tab" data-tab="{key}">{label}</button>'
        for key, label, attr in _TABS
        if getattr(art, attr) is not None
    )
    if show_code:
        buttons += '<button class="side-tab" data-tab="code">代码示例</button>'
    return buttons


# 模板占位符单 pass 替换：re.sub 不重扫替换产物，
# 用户内容（模板引擎类学习产物常含字面 {{...}}）不会被二次注入
_PLACEHOLDER_RE = re.compile(
    r"\{\{(PAGE_TITLE|NAV_HTML|PANEL_OVERVIEW|PANEL_LEARNING_PATH|"
    r"PANEL_RESOURCES|PANEL_CODE|PYGMENTS_CSS|BUILD_META)\}\}"
)


def _warn_degradations(directory: Path, art: Artifacts, tree: CodeTree) -> None:
    """缺件/空 code 树的降级警告到 stderr（规格 §5：tab 隐藏须可见，构建继续）。"""
    missing = [
        name
        for name, value in (
            ("README.md", art.readme),
            ("learning-path.md", art.learning_path),
            ("resources.md", art.resources),
            ("code-examples", art.code_examples),
        )
        if value is None
    ]
    if art.code_examples is not None and not tree.files:
        missing.append("code-examples（空目录）")
    if missing:
        print(
            f"警告：{directory.name} 缺少 {'、'.join(missing)}，对应 tab 将隐藏",
            file=sys.stderr,
        )


def build_html(directory: Path, output: Path | None = None) -> Path:
    """把技术目录组装为自包含 HTML；返回输出路径。

    缺件产物隐藏对应 tab 并向 stderr 打警告；默认输出 <目录名>.html 写入该目录。
    """
    directory = Path(directory)
    art = collect_artifacts(directory)

    overview_html = render_markdown(_read_utf8(art.readme)) if art.readme else ""
    path_html = render_markdown(_read_utf8(art.learning_path)) if art.learning_path else ""
    resources_html = render_markdown(_read_utf8(art.resources)) if art.resources else ""

    # 学习路径面板 = Level 进度条 + 正文
    panel_path = render_progress(extract_levels(path_html)) + path_html if path_html else ""

    tree = build_code_tree(art.code_examples) if art.code_examples else CodeTree(files=[])
    panel_code = render_code_panel(tree)
    _warn_degradations(directory, art, tree)

    # 标题取目录名去 learning- 前缀（learning-kubernetes → kubernetes）；
    # 目录名可含 & < 等 HTML 特殊字符，注入 <title> 前先转义
    tech_name = _html.escape(directory.name.removeprefix("learning-"))
    meta = f"learning-factory {_VERSION} html_builder 构建于 {datetime.now():%Y-%m-%d %H:%M}"

    values = {
        "PAGE_TITLE": f"{tech_name} · Learning Factory",
        "NAV_HTML": _render_nav(art, show_code=bool(tree.files)),
        "PANEL_OVERVIEW": overview_html,
        "PANEL_LEARNING_PATH": panel_path,
        "PANEL_RESOURCES": resources_html,
        "PANEL_CODE": panel_code,
        "PYGMENTS_CSS": highlight_css(),
        "BUILD_META": meta,
    }
    page = _PLACEHOLDER_RE.sub(lambda m: values[m.group(1)], load_template())

    out = output if output is not None else directory / f"{directory.name}.html"
    try:
        out.write_text(page, encoding="utf-8")
    except OSError as exc:
        raise HtmlBuildError(f"写出失败: {out}（{exc.strerror or exc}）") from exc
    return out


# 技术目录判定的专有特征名：README.md 是通用说明文件名，
# 单独出现不再判定为技术目录（防止工厂根目录的说明性 README
# 把批量模式劫持为"构建根目录自身"，子目录静默零产物）
_STRONG_ARTIFACTS = ("learning-path.md", "resources.md", "code-examples")


def _is_tech_dir(path: Path) -> bool:
    """技术目录判定：含任一专有产物名，或至少 2 个产物名。"""
    present = [name for name in ARTIFACT_NAMES if (path / name).exists()]
    return any(name in _STRONG_ARTIFACTS for name in present) or len(present) >= 2


def main(argv: list[str] | None = None) -> int:
    """learning-factory-build 入口：0 成功 / 1 失败 / 2 用法错误。"""
    parser = argparse.ArgumentParser(
        prog="learning-factory-build",
        description="把学习产物目录聚合为一个自包含交互式 HTML 文件",
    )
    parser.add_argument(
        "target",
        help="技术目录（如 Learning-Factory/learning-kubernetes）或工厂根目录（批量）",
    )
    parser.add_argument(
        "--output", default=None, help="输出 HTML 路径（仅单目录模式有效）",
    )
    args = parser.parse_args(argv)

    target = Path(args.target)
    if not target.is_dir():
        print(f"错误：目标不是目录：{target}", file=sys.stderr)
        return 1

    if _is_tech_dir(target):
        try:
            out = build_html(target, Path(args.output) if args.output else None)
        except HtmlBuildError as exc:
            print(f"构建失败：{exc}", file=sys.stderr)
            return 1
        print(f"已构建 {out}")
        return 0

    # 批量模式：目标是工厂根目录
    if args.output:
        parser.error("--output 仅在单目录模式有效")  # SystemExit(2)
    tech_dirs = sorted(
        d for d in target.iterdir() if d.is_dir() and _is_tech_dir(d)
    )
    if not tech_dirs:
        print(f"错误：{target} 下无可构建的技术目录", file=sys.stderr)
        return 1
    failed = 0
    for d in tech_dirs:
        try:
            out = build_html(d)
            print(f"已构建 {out}")
        except HtmlBuildError as exc:
            failed += 1
            print(f"警告：跳过 {d.name}：{exc}", file=sys.stderr)
    # 批量简报汇总行（规格 §4.3：简报须含结果概况）
    print(f"批量构建完成：成功 {len(tech_dirs) - failed} / 失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

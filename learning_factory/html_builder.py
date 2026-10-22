"""
html_builder.py
学习产物单文件 HTML 构建器：把单个技术目录（README.md / learning-path.md /
resources.md / code-examples/）聚合为一个 Notebook Tabs 风格的自包含 HTML。

设计约束（见规格 2026-10-22-html-builder-design.md）：
- 纯函数渲染，零 LLM、零网络；输入目录只读
- 产物 HTML 除 Google Fonts 外零外部引用
"""

import re
from dataclasses import dataclass
from pathlib import Path

import markdown
from pygments import highlight as _pyg_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name


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

    非 UTF-8 文件抛 HtmlBuildError（消息含路径，规格 §5）。
    """
    code_dir = Path(code_dir)
    files: list[CodeFile] = []
    for path in sorted(code_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise HtmlBuildError(f"文件读取失败（非 UTF-8）: {path}") from exc
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


def render_code_panel(tree: CodeTree) -> str:
    """代码 tab 面板：左侧文件树按钮组 + 右侧查看器（默认首文件）。"""
    if not tree.files:
        return ""
    nav = "".join(
        f'<button class="code-file-btn" data-file="cf{i}">'
        f"{f.rel_path}<i class=\"lang-chip\">{f.language}</i></button>"
        for i, f in enumerate(tree.files)
    )
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

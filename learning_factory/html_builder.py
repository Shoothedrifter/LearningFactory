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
from pygments.formatters import HtmlFormatter


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

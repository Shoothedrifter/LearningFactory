"""
html_builder.py
学习产物单文件 HTML 构建器：把单个技术目录（README.md / learning-path.md /
resources.md / code-examples/）聚合为一个 Notebook Tabs 风格的自包含 HTML。

设计约束（见规格 2026-10-22-html-builder-design.md）：
- 纯函数渲染，零 LLM、零网络；输入目录只读
- 产物 HTML 除 Google Fonts 外零外部引用
"""

from dataclasses import dataclass
from pathlib import Path


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

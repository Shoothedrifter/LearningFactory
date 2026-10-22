"""
tests/test_html_builder.py
学习产物单文件 HTML 构建器：收集、渲染、组装的纯函数测试。

对应规格 docs/superpowers/specs/2026-10-22-html-builder-design.md。
构建器零 LLM、零网络、输入目录只读；本文件钉住各纯函数行为。
"""

import pytest

from learning_factory.html_builder import Artifacts, HtmlBuildError, collect_artifacts


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

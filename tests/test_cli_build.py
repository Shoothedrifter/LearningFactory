"""
tests/test_cli_build.py
learning-factory-build CLI：单目录/批量/输出覆盖/退出码。

批量模式下单个目录失败应继续其余目录并返回 1（规格 §5）。
测试直接调用 main(argv)，不经过子进程。
"""

import pytest

from learning_factory.html_builder import HtmlBuildError, main, build_html


def _make_tech_dir(parent, name="learning-demo", bad=False):
    """构造技术目录；bad=True 时写入非 UTF-8 文件制造构建失败。"""
    d = parent / name
    d.mkdir()
    (d / "README.md").write_bytes(b"\xff\xfe\x00bad" if bad else "# x".encode())
    return d


def test_cli_single_dir_builds(tmp_path, capsys):
    """单目录模式：成功返回 0，输出 HTML 落在目录内，stdout 有简报。"""
    d = _make_tech_dir(tmp_path)
    assert main([str(d)]) == 0
    assert (d / "learning-demo.html").exists()
    assert "learning-demo.html" in capsys.readouterr().out


def test_cli_output_override(tmp_path):
    """--output 指定输出路径。"""
    d = _make_tech_dir(tmp_path)
    custom = tmp_path / "custom.html"
    assert main([str(d), "--output", str(custom)]) == 0
    assert custom.exists()


def test_cli_batch_builds_all(tmp_path, capsys):
    """批量模式：根目录下多个技术目录全部构建。"""
    factory = tmp_path / "Factory"
    factory.mkdir()
    for name in ("learning-a", "learning-b"):
        _make_tech_dir(factory, name=name)
    (factory / "not-tech").mkdir()  # 非技术目录应被跳过
    assert main([str(factory)]) == 0
    assert (factory / "learning-a" / "learning-a.html").exists()
    assert (factory / "learning-b" / "learning-b.html").exists()
    assert not (factory / "not-tech" / "not-tech.html").exists()


def test_cli_batch_partial_failure_continues(tmp_path, capsys):
    """批量中单目录失败：其余照常构建，返回 1（Review Focus #4）。"""
    factory = tmp_path / "Factory"
    factory.mkdir()
    good = _make_tech_dir(factory, name="learning-good")
    _make_tech_dir(factory, name="learning-bad", bad=True)
    assert main([str(factory)]) == 1
    assert (good / "learning-good.html").exists()  # 好目录未被坏目录阻断
    assert "learning-bad" in capsys.readouterr().err


def test_cli_output_rejected_in_batch(tmp_path):
    """批量模式传 --output 属用法错误（规格 §4.3）。"""
    factory = tmp_path / "Factory"
    factory.mkdir()
    _make_tech_dir(factory)
    with pytest.raises(SystemExit) as exc:
        main([str(factory), "--output", str(tmp_path / "x.html")])
    assert exc.value.code == 2


def test_cli_single_failure_returns_1(tmp_path, capsys):
    """单目录构建失败：stderr 报错，返回 1。"""
    d = _make_tech_dir(tmp_path, bad=True)
    assert main([str(d)]) == 1
    assert "README.md" in capsys.readouterr().err


def test_cli_not_a_directory(tmp_path, capsys):
    """目标不存在：返回 1 并提示。"""
    assert main([str(tmp_path / "nope")]) == 1
    assert "不是目录" in capsys.readouterr().err


def test_cli_empty_factory_root(tmp_path, capsys):
    """根目录下没有可构建的技术目录：返回 1 并提示。"""
    factory = tmp_path / "Factory"
    factory.mkdir()
    assert main([str(factory)]) == 1
    assert "无可构建" in capsys.readouterr().err

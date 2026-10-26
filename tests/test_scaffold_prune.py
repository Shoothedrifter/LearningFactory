"""
tests/test_scaffold_prune.py
脚手架内置指令 prune：对话内对输出根批量瘦身，复用 html_builder 清理逻辑。

封装标准与自动构建钩子一致：任何内部异常兜底打印，绝不炸会话循环。
"""

from learning_factory import agent


def _make_factory(tmp_path):
    """输出根 + 两个技术目录（README + learning-path 足过技术目录判定）。"""
    factory = tmp_path / "Factory"
    factory.mkdir()
    for name in ("learning-a", "learning-b"):
        d = factory / name
        d.mkdir()
        (d / "README.md").write_text("# x", encoding="utf-8")
        (d / "learning-path.md").write_text("## Level 1: 入门\n\n内容\n", encoding="utf-8")
    return factory


def test_handle_prune_command_prunes(tmp_path, monkeypatch, capsys):
    """prune 指令：对输出根批量清理（y 确认），源产物删除、HTML 保留。"""
    factory = _make_factory(tmp_path)
    monkeypatch.setattr(agent, "get_output_root_dir", lambda: str(factory))
    monkeypatch.setattr("builtins.input", lambda _: "y")
    agent._handle_prune_command()
    for name in ("learning-a", "learning-b"):
        assert (factory / name / f"{name}.html").exists()
        assert not (factory / name / "README.md").exists()
    assert "批量清理完成：成功 2 / 失败 0" in capsys.readouterr().out


def test_handle_prune_command_declined_keeps_sources(tmp_path, monkeypatch):
    """y 之外的回答取消：源文件不动。"""
    factory = _make_factory(tmp_path)
    monkeypatch.setattr(agent, "get_output_root_dir", lambda: str(factory))
    monkeypatch.setattr("builtins.input", lambda _: "n")
    agent._handle_prune_command()
    assert (factory / "learning-a" / "README.md").exists()


def test_handle_prune_command_never_raises(tmp_path, monkeypatch, capsys):
    """内部异常兜底：绝不炸会话循环（与自动构建钩子同标准）。"""
    def _boom():
        raise RuntimeError("内部错误")
    monkeypatch.setattr(agent, "get_output_root_dir", _boom)
    agent._handle_prune_command()  # 不应抛出
    assert "执行失败" in capsys.readouterr().out

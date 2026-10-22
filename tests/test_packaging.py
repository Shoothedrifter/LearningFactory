"""
tests/test_packaging.py
打包与安装守护：prompts 加载的 cwd 无关性（CLI 化缺口 #6）。

pip 安装后用户在任意目录运行 CLI，load_prompt 不能依赖仓库根 cwd
（原实现 PROMPTS_DIR = "prompts" 相对 cwd open，安装后在其他目录
运行必然 FileNotFoundError）。此测试钉住"从任意 cwd 都能读到包内
提示词"，是"人人可安装"链路的最小守护。
"""

from pathlib import Path

from learning_factory import agent, html_builder


def test_load_prompt_is_cwd_independent(tmp_path, monkeypatch):
    """切到空临时目录后 load_prompt 仍能读到包内提示词。"""
    monkeypatch.chdir(tmp_path)
    content = agent.load_prompt("main_agent.md")
    assert len(content) > 100  # 读到的是真实提示词全文而非空串


def test_template_load_is_cwd_independent(tmp_path, monkeypatch):
    """模板随包分发：切到空临时目录仍能读到（同 prompts 的打包守护）。"""
    monkeypatch.chdir(tmp_path)
    tpl = html_builder.load_template()
    assert "{{PAGE_TITLE}}" in tpl  # 读到的是未替换的原始模板


def test_console_script_registered():
    """console script 与依赖已在 pyproject 登记（打包真相）。"""
    pyproject = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    assert 'learning-factory-build = "learning_factory.html_builder:main"' in pyproject
    assert "markdown>=3.6" in pyproject and "pygments>=2.17" in pyproject
    assert '"templates/*.html"' in pyproject

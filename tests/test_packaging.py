"""
tests/test_packaging.py
打包与安装守护：prompts 加载的 cwd 无关性（CLI 化缺口 #6）。

pip 安装后用户在任意目录运行 CLI，load_prompt 不能依赖仓库根 cwd
（原实现 PROMPTS_DIR = "prompts" 相对 cwd open，安装后在其他目录
运行必然 FileNotFoundError）。此测试钉住"从任意 cwd 都能读到包内
提示词"，是"人人可安装"链路的最小守护。
"""

from multi_agent import agent


def test_load_prompt_is_cwd_independent(tmp_path, monkeypatch):
    """切到空临时目录后 load_prompt 仍能读到包内提示词。"""
    monkeypatch.chdir(tmp_path)
    content = agent.load_prompt("main_agent.md")
    assert len(content) > 100  # 读到的是真实提示词全文而非空串

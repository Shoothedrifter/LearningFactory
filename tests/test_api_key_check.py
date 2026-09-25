"""
tests/test_api_key_check.py
启动前置校验：LLM_API_KEY 缺失时启动即给出获取指引并退出，
而非等到首次 API 调用炸出难懂的 401。
"""

import pytest

from learning_factory import agent


def test_missing_key_exits_with_guidance(monkeypatch, capsys):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        agent.ensure_api_key()
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "LLM_API_KEY" in err
    assert "bigmodel.cn" in err          # 默认供应商（智谱 GLM）获取地址
    assert "OpenAI 兼容" in err          # 换供应商线索（系统不绑定智谱）
    assert ".env" in err                 # 配置方式指引

def test_present_key_passes_silently(monkeypatch, capsys):
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    agent.ensure_api_key()               # 不抛即通过
    assert capsys.readouterr().err == ""

async def test_main_exits_before_banner_when_key_missing(monkeypatch):
    """main() 在打印横幅之前完成校验（用户无 key 时看不到假启动）。"""
    import asyncio
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        await agent.main(resume=None)

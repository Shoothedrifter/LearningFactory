"""
tests/test_no_glm_names.py
供应商中立钉住：包源码零 GLM_ 字样（无豁免——旧名兼容层已于 0.2.0 移除，
config.py 也不允许出现），旧变量名不再被读取。
"""

import os

from pathlib import Path

from learning_factory import agent, config


def test_no_glm_names_in_source():
    """钉住：包源码零 GLM_ 字样（字符串与注释都算），无任何豁免——
    旧名兼容层已整体移除，防未来代码把旧名带回来。"""
    pkg = Path(config.__file__).parent
    offenders = [
        f"{p.relative_to(pkg.parent)}:{i + 1}: {line.strip()}"
        for p in sorted(pkg.rglob("*.py"))
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines())
        if "GLM_" in line
    ]
    assert offenders == [], "发现 GLM_ 残留:\n" + "\n".join(offenders)


def test_legacy_names_no_longer_read(monkeypatch):
    """旧变量名不再被读取：只设旧 GLM_API_KEY 时 ensure_api_key 照样拦截，
    引导用户改用新名配置（兼容层移除后的预期行为）。"""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("GLM_API_KEY", "legacy-key")
    try:
        agent.ensure_api_key()
    except SystemExit:
        return
    raise AssertionError("旧变量名不应再通过启动校验")

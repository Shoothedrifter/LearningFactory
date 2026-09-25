"""
tests/test_legacy_env_compat.py
旧 GLM_* 变量名兼容层：启动时一次性映射到新 LLM_*/MCP_* 名（0.2.0 B 层，spec
docs/superpowers/specs/2026-09-26-vendor-neutral-0.2.0-design.md）。
映射后旧名删除（幂等），命中时 stderr 恰一行迁移提示。
"""

import importlib
import os

import pytest

from learning_factory import agent, config, server


@pytest.mark.parametrize("old,new", sorted(config._LEGACY_ENV_MAP.items()))
def test_legacy_name_maps_to_new(old, new, monkeypatch):
    """8 组旧名逐一映射：旧名有值且新名未设 → 新名获得该值，旧名删除。"""
    monkeypatch.delenv(new, raising=False)
    monkeypatch.setenv(old, "legacy-value")
    config.migrate_legacy_env()
    assert os.environ[new] == "legacy-value"
    assert old not in os.environ       # 删除旧名 → 重复调用无命中（幂等来源）


def test_new_name_wins_when_both_set(monkeypatch):
    """新旧名都设：新名胜出；旧名未迁移、保留原值。"""
    monkeypatch.setenv("GLM_API_KEY", "old")
    monkeypatch.setenv("LLM_API_KEY", "new")
    config.migrate_legacy_env()
    assert os.environ["LLM_API_KEY"] == "new"
    assert os.environ["GLM_API_KEY"] == "old"


def test_migrate_is_idempotent(monkeypatch, capsys):
    """第二次调用无提示（旧名首次已删，不再命中）。"""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("GLM_API_KEY", "v")
    config.migrate_legacy_env()
    capsys.readouterr()                # 清掉第一次的提示
    config.migrate_legacy_env()
    assert capsys.readouterr().err == ""


def test_migration_notice_is_one_stderr_line(monkeypatch, capsys):
    """命中多个旧名也只打一行，且列出全部命中与新名指引。"""
    for new in ("LLM_API_KEY", "LLM_BASE_URL"):
        monkeypatch.delenv(new, raising=False)
    monkeypatch.setenv("GLM_API_KEY", "v")
    monkeypatch.setenv("GLM_BASE_URL", "https://x/")
    config.migrate_legacy_env()
    err = capsys.readouterr().err
    lines = [ln for ln in err.splitlines() if ln.strip()]
    assert len(lines) == 1
    assert "GLM_API_KEY" in err and "GLM_BASE_URL" in err
    assert "LLM_" in err               # 指引迁移到新命名


def test_no_notice_when_no_legacy_names(monkeypatch, capsys):
    """全部旧名缺席：零输出。"""
    for old in config._LEGACY_ENV_MAP:
        monkeypatch.delenv(old, raising=False)
    config.migrate_legacy_env()
    assert capsys.readouterr().err == ""


def test_ensure_api_key_passes_with_legacy_name(monkeypatch):
    """调用顺序钉住：ensure_api_key 先迁移再校验——旧 .env 用户不被误拦。"""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("GLM_API_KEY", "legacy-key")
    agent.ensure_api_key()             # 不抛 SystemExit 即通过


def test_no_glm_names_in_source_except_config():
    """钉住：包源码零 GLM_ 字样（字符串与注释都算），唯 config.py 豁免——
    旧名只允许活在 _LEGACY_ENV_MAP 一处（spec 验收标准）。"""
    from pathlib import Path
    pkg = Path(config.__file__).parent
    offenders = [
        f"{p.relative_to(pkg.parent)}:{i + 1}: {line.strip()}"
        for p in sorted(pkg.rglob("*.py"))
        if p != pkg / "config.py"
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines())
        if "GLM_" in line
    ]
    assert offenders == [], "发现 GLM_ 残留:\n" + "\n".join(offenders)


def test_server_module_level_migrate(monkeypatch, capsys, tmp_path):
    """uvicorn 直启（非 __main__）不经过 ensure_api_key——模块导入期必须
    自带旧名迁移，否则旧 .env 用户首条消息 401（0.1.x 直读旧名可用，
    属改名引入的回归，终审 Important）。"""
    # chdir 到空目录再 reload：模块级 load_dotenv 只认 cwd 的 .env，
    # 隔离开发者真实 .env（若含新名，迁移会因新名已设而跳过导致假红）
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("GLM_API_KEY", "legacy-key")
    importlib.reload(server)
    assert os.environ["LLM_API_KEY"] == "legacy-key"
    assert "GLM_API_KEY" not in os.environ

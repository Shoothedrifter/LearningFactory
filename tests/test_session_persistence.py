"""
tests/test_session_persistence.py
CLI 会话持久化：逐轮追加到家目录 JSONL，--resume 恢复。
SESSIONS_DIR 经 monkeypatch 重定向到 tmp_path，不污染真实家目录。
"""

import json

from learning_factory import session


def test_append_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "SESSIONS_DIR", tmp_path)
    path = session.new_session_path()
    msgs = [
        {"role": "user", "content": "学一下 PyTorch"},
        {"role": "assistant", "content": "好的，开始研究…"},
    ]
    for m in msgs:
        session.append_message(path, m)
    assert session.load_session(path) == msgs

def test_load_skips_corrupt_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "SESSIONS_DIR", tmp_path)
    path = session.new_session_path()
    session.append_message(path, {"role": "user", "content": "a"})
    path.write_text(path.read_text() + "{坏掉的行\n", encoding="utf-8")
    session.append_message(path, {"role": "assistant", "content": "b"})
    assert session.load_session(path) == [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
    ]

def test_load_skips_non_message_lines(tmp_path, monkeypatch):
    """合法 JSON 但非消息形态（数字/空 dict/字符串）的行静默跳过。

    手编或损坏的会话文件混入这类行时，不能进入 messages——
    否则 resume 时在 conversation_history[-1]["role"] 处崩溃。
    """
    monkeypatch.setattr(session, "SESSIONS_DIR", tmp_path)
    path = session.new_session_path()
    session.append_message(path, {"role": "user", "content": "a"})
    path.write_text(path.read_text() + "123\n{}\n\"x\"\n", encoding="utf-8")
    session.append_message(path, {"role": "assistant", "content": "b"})
    assert session.load_session(path) == [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
    ]

def test_latest_session_picks_newest(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "SESSIONS_DIR", tmp_path)
    assert session.latest_session_path() is None            # 空目录
    older = tmp_path / "20260101-000000.jsonl"; older.write_text("{}", encoding="utf-8")
    newer = tmp_path / "20260102-000000.jsonl"; newer.write_text("{}", encoding="utf-8")
    assert session.latest_session_path() == newer           # 文件名降序即时间序

async def test_main_resume_restores_history(tmp_path, monkeypatch, patch_openai, capsys):
    """--resume 集成：恢复的旧消息进入对话历史，随请求发给模型。"""
    from learning_factory import agent

    sess_dir = tmp_path / "sessions"; sess_dir.mkdir()
    old = sess_dir / "old.jsonl"
    session.append_message(old, {"role": "user", "content": "旧问题"})
    session.append_message(old, {"role": "assistant", "content": "旧回答"})

    monkeypatch.setattr(session, "SESSIONS_DIR", sess_dir)
    # CI 无 .env / 真实 key：补一个假 key 让 ensure_api_key() 前置校验通过
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    monkeypatch.setattr(agent, "load_prompt", lambda f: "测试提示词")
    monkeypatch.setattr(agent, "load_skills", lambda: "")
    inputs = iter(["新问题", "exit"])
    monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
    # 假流式主 Agent：记录入参 messages，yield 一条 main 的 answer 事件
    # （main() 已切 run_main_agent_stream，mock 形态随调用方对齐）
    captured = {}

    async def fake_run_main_agent_stream(**kwargs):
        captured["messages"] = list(kwargs["messages"])
        yield json.dumps({"type": "answer", "agent": "main", "content": "新回答"},
                         ensure_ascii=False)

    monkeypatch.setattr(agent, "run_main_agent_stream", fake_run_main_agent_stream)
    patch_openai()  # run_main_agent_stream 已替换，这里仅兜底防真实客户端构造

    await agent.main(resume=str(old))

    out = capsys.readouterr().out
    assert "已恢复会话 old.jsonl" in out
    assert "2 条消息" in out
    # 恢复的旧历史（旧问题/旧回答）+ 新问题 → 发给模型，长度 ≥ 2 且含旧消息
    assert len(captured["messages"]) >= 2
    assert captured["messages"][0] == {"role": "user", "content": "旧问题"}
    # 逐轮落盘：恢复会话后新一轮的 user/assistant 消息追加进同一文件
    assert len(session.load_session(old)) == 4


async def test_main_resume_trims_trailing_orphan_user(tmp_path, monkeypatch, patch_openai, capsys):
    """旧会话尾部孤儿 user（异常轮次已落盘未回滚）resume 后不进请求上下文。"""
    from learning_factory import agent

    sess_dir = tmp_path / "sessions"; sess_dir.mkdir()
    old = sess_dir / "orphan.jsonl"
    session.append_message(old, {"role": "user", "content": "旧问题"})
    session.append_message(old, {"role": "assistant", "content": "旧回答"})
    # 模拟异常轮次残留：user 已落盘，但模型回答未来得及写入
    session.append_message(old, {"role": "user", "content": "孤儿问题"})

    monkeypatch.setattr(session, "SESSIONS_DIR", sess_dir)
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    monkeypatch.setattr(agent, "load_prompt", lambda f: "测试提示词")
    monkeypatch.setattr(agent, "load_skills", lambda: "")
    inputs = iter(["新问题", "exit"])
    monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
    captured = {}

    async def fake_run_main_agent_stream(**kwargs):
        captured["messages"] = list(kwargs["messages"])
        yield json.dumps({"type": "answer", "agent": "main", "content": "新回答"},
                         ensure_ascii=False)

    monkeypatch.setattr(agent, "run_main_agent_stream", fake_run_main_agent_stream)
    patch_openai()

    await agent.main(resume=str(old))

    msgs = captured["messages"]
    # 孤儿 user 不进上下文：内容缺席，且历史里不出现连续两条 user
    # （恢复部分以旧回答收尾，新问题正常作为尾部 user 进入）
    assert all(m["content"] != "孤儿问题" for m in msgs)
    assert msgs[-1] == {"role": "user", "content": "新问题"}
    assert msgs[-2] == {"role": "assistant", "content": "旧回答"}
    roles = [m["role"] for m in msgs]
    assert not any(a == "user" and b == "user" for a, b in zip(roles, roles[1:]))


# ── 装载清洗：孤儿 user 的中段封存（终审 2026-09-24 Minor #1）──
# 异常轮次磁盘已落盘孤儿 user、内存已 pop；同会话继续对话会把孤儿压进中段，
# 尾部裁剪永远够不到——清洗统一规则：连续 user 段压缩为段尾一条，
# 整体尾部 user 段压到 0（新一轮输入前不应有未回应 user）。磁盘永不改写。


def _u(c):
    return {"role": "user", "content": c}


def _a(c):
    return {"role": "assistant", "content": c}


def test_sanitize_compresses_mid_user_run():
    """中段连续 user（孤儿被后续轮次封存）：压缩为段尾一条，孤儿缺席。"""
    cleaned = session.sanitize_session_messages(
        [_u("问1"), _a("答1"), _u("孤儿问题"), _u("问3"), _a("答3")]
    )
    assert cleaned == [_u("问1"), _a("答1"), _u("问3"), _a("答3")]


def test_sanitize_drops_trailing_users():
    """整体尾部连续 user（异常退出残留）：全部裁掉。"""
    cleaned = session.sanitize_session_messages([_u("问1"), _a("答1"), _u("孤儿")])
    assert cleaned == [_u("问1"), _a("答1")]


def test_sanitize_clean_history_untouched():
    """干净的交替历史原样返回（幂等）。"""
    msgs = [_u("问1"), _a("答1"), _u("问2"), _a("答2")]
    assert session.sanitize_session_messages(msgs) == msgs


async def test_main_resume_squeezes_mid_orphan_user(tmp_path, monkeypatch, patch_openai):
    """中段孤儿会话 resume：孤儿不进请求上下文，历史无连续 user。"""
    from learning_factory import agent

    sess_dir = tmp_path / "sessions"; sess_dir.mkdir()
    old = sess_dir / "mid-orphan.jsonl"
    for m in [_u("问1"), _a("答1"), _u("孤儿问题"), _u("问3"), _a("答3")]:
        session.append_message(old, m)

    monkeypatch.setattr(session, "SESSIONS_DIR", sess_dir)
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    monkeypatch.setattr(agent, "load_prompt", lambda f: "测试提示词")
    monkeypatch.setattr(agent, "load_skills", lambda: "")
    inputs = iter(["新问题", "exit"])
    monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
    captured = {}

    async def fake_run_main_agent_stream(**kwargs):
        captured["messages"] = list(kwargs["messages"])
        yield json.dumps({"type": "answer", "agent": "main", "content": "新回答"},
                         ensure_ascii=False)

    monkeypatch.setattr(agent, "run_main_agent_stream", fake_run_main_agent_stream)
    patch_openai()

    await agent.main(resume=str(old))

    msgs = captured["messages"]
    # 孤儿缺席（中段封存被清洗）；保留的问3/答3 原样进上下文
    assert all(m["content"] != "孤儿问题" for m in msgs)
    assert {"role": "user", "content": "问3"} in msgs
    roles = [m["role"] for m in msgs]
    assert not any(a == "user" and b == "user" for a, b in zip(roles, roles[1:]))

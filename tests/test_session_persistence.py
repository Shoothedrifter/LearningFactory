"""
tests/test_session_persistence.py
CLI 会话持久化：逐轮追加到家目录 JSONL，--resume 恢复。
SESSIONS_DIR 经 monkeypatch 重定向到 tmp_path，不污染真实家目录。
"""

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
    monkeypatch.setenv("GLM_API_KEY", "fake-key")
    monkeypatch.setattr(agent, "load_prompt", lambda f: "测试提示词")
    monkeypatch.setattr(agent, "load_skills", lambda: "")
    inputs = iter(["新问题", "exit"])
    monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
    # 假主 Agent：记录入参 messages，直接返回答案（不经真实模型）
    captured = {}

    async def fake_run_main_agent(**kwargs):
        captured["messages"] = list(kwargs["messages"])
        return "新回答"

    monkeypatch.setattr(agent, "run_main_agent", fake_run_main_agent)
    patch_openai()  # run_main_agent 已替换，这里仅兜底防真实客户端构造

    await agent.main(resume=str(old))

    out = capsys.readouterr().out
    assert "已恢复会话 old.jsonl" in out
    assert "2 条消息" in out
    # 恢复的旧历史（旧问题/旧回答）+ 新问题 → 发给模型，长度 ≥ 2 且含旧消息
    assert len(captured["messages"]) >= 2
    assert captured["messages"][0] == {"role": "user", "content": "旧问题"}
    # 逐轮落盘：恢复会话后新一轮的 user/assistant 消息追加进同一文件
    assert len(session.load_session(old)) == 4

"""
learning_factory/session.py
CLI 会话持久化：对话历史逐轮追加到家目录 JSONL，崩溃也保留已写轮次；
--resume 恢复最近会话或指定文件。家目录不污染任意运行 cwd（pipx 场景）。
"""

import json
from datetime import datetime
from pathlib import Path

SESSIONS_DIR = Path.home() / ".learning_factory" / "sessions"


def new_session_path() -> Path:
    """创建新会话文件路径（确保目录存在，文件名按秒防撞）。"""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return SESSIONS_DIR / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}.jsonl"


def append_message(path: Path, message: dict) -> None:
    """追加一条消息（一行 JSON，立即落盘不留缓冲）。"""
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(message, ensure_ascii=False) + "\n")


def load_session(path: Path) -> list:
    """读取会话全部消息；损坏行与非消息行跳过（手编文件容错）。"""
    if not path.exists():
        return []
    messages = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(line)
            # 只收消息形态的行（dict 且含 role），其余合法 JSON（数字/字符串/空
            # dict 等）静默跳过——否则 resume 时在 [-1]["role"] 处崩溃
            if isinstance(obj, dict) and "role" in obj:
                messages.append(obj)
        except json.JSONDecodeError:
            continue
    return messages


def latest_session_path():
    """最近一次会话路径（文件名降序即时间序）；无会话返回 None。"""
    if not SESSIONS_DIR.exists():
        return None
    files = sorted(SESSIONS_DIR.glob("*.jsonl"), reverse=True)
    return files[0] if files else None

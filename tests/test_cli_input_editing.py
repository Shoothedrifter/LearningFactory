"""
tests/test_cli_input_editing.py
钉住 CLI 输入行的行编辑能力：方向键等按键必须由 readline 接管，
而不是被内核 tty 当普通字节回显成 ^[[D 之类的转义序列。

病灶：agent.py 未导入 readline 模块时，input() 不启用 GNU readline
行编辑（CPython 只在 readline 模块被导入后才安装其钩子），左方向键
的 \x1b[D 直接落入输入缓冲并被回显，用户看到 ^[[D 且光标不动。

测试用 pty 驱动真实子进程（import learning_factory.agent 后 input()），
发送 "ab" + 左方向键 + "x" + 回车：readline 生效时左键移动光标，
x 插入中间，input() 返回 'axb'；失效时返回 'ab\x1b[Dx'。
"""

import os
import pty
import select
import subprocess
import sys

import pytest


def _has_readline() -> bool:
    """当前解释器环境能否导入 readline（决定测试是否有意义）。"""
    try:
        import readline  # noqa: F401
        return True
    except ImportError:
        return False


def _read_until(master, marker: str, timeout: float = 5.0) -> str:
    """从 pty 读输出直到出现 marker 或超时，返回累计输出。"""
    buf = ""
    while marker not in buf:
        r, _, _ = select.select([master], [], [], timeout)
        if not r:
            break  # 超时：返回已有内容，由调用方断言
        try:
            chunk = os.read(master, 4096)
        except OSError:
            break  # 子进程已退出
        if not chunk:
            break
        buf += chunk.decode(errors="replace")
    return buf


def _drive_input_editing(tmp_path) -> str:
    """在 pty 里跑真实解释器：导入 CLI 模块后 input()，发送带方向键的按键序列。"""
    code = (
        "import learning_factory.agent as agent_mod\n"
        "s = input('P: ')\n"
        "print('GOT:', repr(s))\n"
    )
    master, slave = pty.openpty()
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        stdin=slave, stdout=slave, stderr=slave,
        cwd=str(tmp_path), close_fds=True,
    )
    os.close(slave)
    try:
        # 等子进程打印提示符（确保 input() 已就绪）再发按键
        _read_until(master, "P: ")
        os.write(master, b"ab\x1b[Dx\r")
        out = _read_until(master, "GOT:")
        # 收尾：读干净剩余输出，等子进程退出
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        out += _read_until(master, "GOT:")
        return out.replace("\r\n", "\n").replace("\r", "\n")
    finally:
        os.close(master)
        if proc.poll() is None:
            proc.kill()
            proc.wait()


@pytest.mark.skipif(sys.platform == "win32", reason="pty/readline 为 Unix 机制")
@pytest.mark.skipif(not _has_readline(), reason="平台无 readline 模块时无从谈起行编辑")
def test_arrow_keys_move_cursor(tmp_path):
    """左方向键必须移动光标（readline 生效），而非把 \\x1b[D 送进输入行。"""
    out = _drive_input_editing(tmp_path)
    assert "GOT: 'axb'" in out, f"输入行未启用行编辑，实际输出：{out!r}"

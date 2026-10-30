"""
tests/helpers.py
测试辅助：伪造 OpenAI 响应结构 + 并发度记录器 + skill 脚本加载。

假对象的字段与 agent.py 实际读取的字段一一对应：
  response.choices[0].message.content
  response.choices[0].message.tool_calls（列表，元素含 .id / .function.name / .function.arguments）
  response.choices[0].finish_reason
"""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

# skill 独立脚本位置（仓库根下 .agents/skills/learning-factory/scripts/）
REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / ".agents" / "skills" / "learning-factory" / "scripts" / "build_html.py"

_build_html_cache = None


def load_build_html():
    """按文件位置加载 skill 脚本 build_html.py，返回缓存的模块对象。

    供迁移后的 test_html_builder / test_cli_build 模块级解包符号用
    （脚本不在包内，不能 from ... import）；需要观察导入期降级行为的
    测试改用 conftest.build_html_module_reload。

    模块必须注册进 sys.modules：脚本用了 from __future__ import
    annotations，dataclass 解析字符串注解时会查 sys.modules[cls.__module__]。
    """
    global _build_html_cache
    if _build_html_cache is None:
        spec = importlib.util.spec_from_file_location("lf_skill_build_html", SCRIPT_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(spec.name, None)
            raise
        _build_html_cache = module
    return _build_html_cache


def make_tool_call(call_id: str, name: str, **args):
    """构造一个 tool_call 假对象，arguments 为 JSON 字符串（与 OpenAI SDK 一致）。"""
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(
            name=name,
            arguments=json.dumps(args, ensure_ascii=False),
        ),
    )


def make_tool_calls_response(tool_calls: list):
    """构造"模型要求调用工具"的响应（finish_reason=tool_calls）。"""
    msg = SimpleNamespace(content=None, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="tool_calls")])


def make_text_response(text: str):
    """构造"模型返回最终文本"的响应（finish_reason=stop）。"""
    msg = SimpleNamespace(content=text, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")])


class ConcurrencyRecorder:
    """记录异步任务的并发度：进入 +1、离开 -1，max_active 为历史峰值。"""

    def __init__(self):
        self.active = 0
        self.max_active = 0

    def enter(self):
        self.active += 1
        self.max_active = max(self.max_active, self.active)

    def exit(self):
        self.active -= 1


def make_rate_limit_error():
    """构造真实的 openai.RateLimitError（429），用于 dispatch 退避重试测试。"""
    import httpx
    import openai

    request = httpx.Request("POST", "https://api.test.local/v1/chat/completions")
    response = httpx.Response(429, request=request)
    return openai.RateLimitError("Error code: 429 - 测试限流", response=response, body=None)

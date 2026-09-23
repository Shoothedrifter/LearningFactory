"""
tests/helpers.py
测试辅助：伪造 OpenAI 响应结构 + 并发度记录器。

假对象的字段与 agent.py 实际读取的字段一一对应：
  response.choices[0].message.content
  response.choices[0].message.tool_calls（列表，元素含 .id / .function.name / .function.arguments）
  response.choices[0].finish_reason
"""

import json
from types import SimpleNamespace


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

"""
tests/conftest.py
提供 patch_openai fixture：伪造 openai.AsyncOpenAI，让被测代码里的
chat.completions.create 按顺序返回预设响应。

agent.py 的 run_main_agent / run_main_agent_stream 在函数体内执行
`from openai import AsyncOpenAI`（每次调用时取 openai 模块属性），
因此 patch openai.AsyncOpenAI 即可生效。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def patch_openai():
    """工厂 fixture。用法：

        client = patch_openai(resp1, resp2)
        ...  # 运行被测代码，第 1 次 create 返回 resp1，第 2 次返回 resp2
        client.chat.completions.create.call_args_list  # 每次调用的参数记录
    """

    def _factory(*responses):
        fake_client = MagicMock()
        fake_client.chat.completions.create = AsyncMock(side_effect=list(responses))
        patch("openai.AsyncOpenAI", return_value=fake_client).start()
        return fake_client

    yield _factory
    patch.stopall()

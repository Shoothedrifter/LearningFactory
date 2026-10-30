"""
tests/conftest.py
提供 patch_openai fixture：伪造 openai.AsyncOpenAI，让被测代码里的
chat.completions.create 按顺序返回预设响应。

agent.py 的 run_main_agent / run_main_agent_stream 在函数体内执行
`from openai import AsyncOpenAI`（每次调用时取 openai 模块属性），
因此 patch openai.AsyncOpenAI 即可生效。

另提供 skill 脚本 build_html.py 的两个加载 fixture（spec 见
2026-10-30-skill-adaptation-design.md §6.4 / 计划 Task 1 Interfaces）。
"""

import importlib.util
import sys

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from helpers import SCRIPT_PATH, load_build_html


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


@pytest.fixture(scope="session")
def build_html_module():
    """skill 脚本 build_html.py 的会话级共享模块实例（带缓存）。"""
    return load_build_html()


@pytest.fixture
def build_html_module_reload():
    """强制重载工厂：测试先用 monkeypatch 篡改 sys.modules（如把 pygments
    置 None），再调用本工厂获得全新模块对象，观察导入期降级行为。

    teardown 清除全部副作用，两组都要处理：
    1. fresh 模块可能在其（依赖被禁的）运行窗口内首次 import
       markdown.extensions.codehilite——该模块顶层 try-import pygments
       失败后会把模块级降级标志永久缓存进 sys.modules，必须弹出。
    2. 只弹 codehilite 不够：重 import 会产生全新的
       CodeHiliteExtension 类对象，而未弹出的 fenced_code 模块仍绑定
       旧类引用——fenced_code.py 用 isinstance(ext, CodeHiliteExtension)
       匹配扩展，身份分裂后委托永远失败（fenced 代码块不再高亮）。
       因此 fenced_code 必须一并弹出，两者下次一起重新 import、身份一致。
    """
    loaded = []

    def _reload():
        spec = importlib.util.spec_from_file_location("lf_skill_build_html_fresh", SCRIPT_PATH)
        module = importlib.util.module_from_spec(spec)
        # 注册进 sys.modules：脚本注解为字符串（future annotations），
        # dataclass 解析时按模块名查命名空间，不注册会 NoneType 崩
        sys.modules[spec.name] = module
        loaded.append(spec.name)
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(spec.name, None)
            raise
        return module

    yield _reload

    for name in loaded:
        sys.modules.pop(name, None)
    sys.modules.pop("markdown.extensions.codehilite", None)
    sys.modules.pop("markdown.extensions.fenced_code", None)

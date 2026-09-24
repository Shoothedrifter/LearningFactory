"""
tests/test_branding.py
对外系统名统一钉住为「学习工厂」（2026-09-24 用户拍板，丢弃「多智能体系统」旧称）。
CLI 启动横幅的断言在 test_cli_render.py 的 main() 集成测试中，此处钉 Web 侧两处。
"""

from pathlib import Path

from learning_factory.server import app as web_app

# 前端页面路径（与 server.py 的 STATIC_DIR 同构）
_INDEX_HTML = Path(__file__).parent.parent / "learning_factory" / "static" / "index.html"


def test_web_app_title_is_learning_factory():
    """FastAPI title 显示在 /docs OpenAPI 页，须与系统名一致。"""
    assert web_app.title == "学习工厂"


def test_index_html_title_is_learning_factory():
    """浏览器标签页 title 须与系统名一致。"""
    assert "<title>学习工厂</title>" in _INDEX_HTML.read_text(encoding="utf-8")

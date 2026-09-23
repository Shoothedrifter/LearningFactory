"""
tests/test_skill_output_rewrite.py
SKILL.md 输出段与 P3 对齐：写入指示从主 Agent 分块写入改为 dispatch file_writer。
（SKILL.md 是提示词数据文件；轻量内容断言防止指示回退到已证死循环的旧文案。）
"""

from pathlib import Path


def test_skill_md_directs_file_writer():
    """输出段指示 dispatch file_writer；旧分块细则文案已移除。"""
    text = Path("skills/learning-a-tool/SKILL.md").read_text(encoding="utf-8")
    assert "file_writer" in text
    assert "Write the first chunk" not in text  # 旧主 Agent 分块细则已下沉

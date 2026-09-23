"""
tests/test_skill_tools.py
Skill 渐进披露加载工具（tools/skills.py）的 TDD 测试。

三层渐进披露：
  第一层  get_skill_manifest —— name + description 清单（常驻 system prompt）
  第二层  load_skill(skill_name) —— SKILL.md 全文 + 参考文件指引
  第三层  load_skill(skill_name, reference=...) —— 参考文件全文
"""

import asyncio

from multi_agent.tools import skills as skills_mod
from multi_agent.tools import TOOL_REGISTRY


def _make_skill(root, name, description="一个测试技能", body="# 工作流正文", refs=None):
    """在临时目录构造一个技能目录（frontmatter + 正文 + 可选参考文件）。"""
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    frontmatter = f"---\nname: {name}\ndescription: {description}\n---\n"
    (skill_dir / "SKILL.md").write_text(frontmatter + body, encoding="utf-8")
    if refs:
        refs_dir = skill_dir / "references"
        refs_dir.mkdir()
        for ref_name, ref_body in refs.items():
            (refs_dir / ref_name).write_text(ref_body, encoding="utf-8")
    return skill_dir


def _run(coro):
    """同步执行异步工具函数。"""
    return asyncio.run(coro)


def test_frontmatter_parsing(tmp_path):
    """frontmatter 解析：提取 name/description；无 frontmatter 返回空 dict。"""
    text = "---\nname: a\ndescription: 描述内容\n---\n\n# 正文"
    assert skills_mod._parse_frontmatter(text) == {"name": "a", "description": "描述内容"}
    assert skills_mod._parse_frontmatter("# 没有 frontmatter") == {}


def test_manifest_lists_name_and_description(tmp_path, monkeypatch):
    """清单只含 name + description，不含正文（第一层不泄露第二层内容）。"""
    monkeypatch.setattr(skills_mod, "SKILLS_DIR", tmp_path)
    _make_skill(tmp_path, "skill-one", description="第一个技能", body="# 机密正文不应出现")
    manifest = skills_mod.get_skill_manifest()
    assert manifest == [{"name": "skill-one", "description": "第一个技能"}]


def test_manifest_fallback_without_frontmatter(tmp_path, monkeypatch):
    """无 frontmatter 时 name 回退为目录名、description 回退空串。"""
    monkeypatch.setattr(skills_mod, "SKILLS_DIR", tmp_path)
    skill_dir = tmp_path / "bare-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# 只有正文", encoding="utf-8")
    manifest = skills_mod.get_skill_manifest()
    assert manifest == [{"name": "bare-skill", "description": ""}]


def test_manifest_empty_when_no_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(skills_mod, "SKILLS_DIR", tmp_path / "不存在")
    assert skills_mod.get_skill_manifest() == []


def test_load_skill_returns_full_body_and_ref_hint(tmp_path, monkeypatch):
    """第二层：返回 SKILL.md 全文，尾部附参考文件加载指引。"""
    monkeypatch.setattr(skills_mod, "SKILLS_DIR", tmp_path)
    _make_skill(tmp_path, "skill-one", body="# 完整工作流", refs={"extra.md": "# 参考内容"})
    result = _run(skills_mod.load_skill(skill_name="skill-one"))
    assert "# 完整工作流" in result
    assert "extra.md" in result  # 参考文件被列入指引


def test_load_skill_reference_file(tmp_path, monkeypatch):
    """第三层：reference 参数返回对应参考文件全文。"""
    monkeypatch.setattr(skills_mod, "SKILLS_DIR", tmp_path)
    _make_skill(tmp_path, "skill-one", refs={"extra.md": "# 五级渐进结构"})
    result = _run(skills_mod.load_skill(skill_name="skill-one", reference="extra.md"))
    assert result == "# 五级渐进结构"


def test_load_skill_unknown_errors(tmp_path, monkeypatch):
    """未知技能 / 未知参考文件：返回带可用列表的错误串。"""
    monkeypatch.setattr(skills_mod, "SKILLS_DIR", tmp_path)
    _make_skill(tmp_path, "skill-one", refs={"extra.md": "x"})
    unknown_skill = _run(skills_mod.load_skill(skill_name="nope"))
    assert "未知技能" in unknown_skill and "skill-one" in unknown_skill
    unknown_ref = _run(skills_mod.load_skill(skill_name="skill-one", reference="nope.md"))
    assert "未知参考文件" in unknown_ref and "extra.md" in unknown_ref


def test_load_skill_registered():
    """load_skill 必须注册进 TOOL_REGISTRY（主 Agent 经 _run_plain_tool 调用）。"""
    assert "load_skill" in TOOL_REGISTRY

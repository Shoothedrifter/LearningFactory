"""
tests/test_skill_package.py
skill 包结构守护：SKILL.md frontmatter 合规（agentskills.io 开放标准）、
正文行数上限、description 双语触发词、包内文件供应商中立。

frontmatter 解析不引第三方 YAML 依赖，按 "---" 围栏取 `key:` 前缀。
完整产物名/引用一致性守护见 test_skill_integrity.py（Task 3）。
"""

from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent / ".agents" / "skills" / "learning-factory"
SKILL_MD = SKILL_DIR / "SKILL.md"

# agentskills.io 开放标准允许的全部 frontmatter 字段（SKILL.md frontmatter 限 6 字段）
FRONTMATTER_STANDARD_FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}


def _frontmatter_fields(text):
    """解析 SKILL.md 顶部 --- 围栏内的字段名集合。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return set()
    fields = set()
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        if line and not line[0].isspace() and ":" in line:
            fields.add(line.split(":", 1)[0].strip())
    return fields


def _frontmatter_value(text, key):
    """取 frontmatter 中某字段的第一行值（多行值只取首行，本用途足够）。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for line in lines[1:]:
        if line.strip() == "---":
            return ""
        if line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip()
    return ""


def test_frontmatter_standard_fields_only():
    """frontmatter 只用开放标准字段，且必含 name 与 description。"""
    fields = _frontmatter_fields(SKILL_MD.read_text(encoding="utf-8"))
    extra = fields - FRONTMATTER_STANDARD_FIELDS
    assert extra == set(), f"frontmatter 出现非标准字段: {sorted(extra)}"
    assert "name" in fields and "description" in fields


def test_skill_md_under_500_lines():
    """SKILL.md 总行数 < 500（渐进式披露，细节放 references）。"""
    assert len(SKILL_MD.read_text(encoding="utf-8").splitlines()) < 500


def test_description_bilingual_triggers():
    """description 含双语触发词：英文 "learning plan" 与中文 "学习"（Review Focus #3）。"""
    desc = _frontmatter_value(SKILL_MD.read_text(encoding="utf-8"), "description").lower()
    assert "learning plan" in desc
    assert "学习" in desc


def test_skill_files_vendor_neutral():
    """skill 包内全部文本文件不含 "bigmodel"（供应商中立，guard 精神前置自查）。"""
    offenders = [
        f"{p.relative_to(SKILL_DIR)}:{i + 1}: {line.strip()}"
        for p in sorted(SKILL_DIR.rglob("*"))
        if p.is_file() and p.suffix in {".md", ".py", ".json", ".toml", ".txt"}
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines())
        if "bigmodel" in line.lower()
    ]
    assert offenders == [], "发现供应商名残留:\n" + "\n".join(offenders)

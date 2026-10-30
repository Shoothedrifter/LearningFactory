"""
tests/test_skill_package.py
skill 包结构守护：SKILL.md frontmatter 合规（agentskills.io 开放标准）、
正文行数上限、description 双语触发词、包内文件供应商中立、
相对路径引用存在性、产物名与脚本常量一致、五级标题跨文件一致
（spec §6.5 产物规范单一事实源）。

frontmatter 解析不引第三方 YAML 依赖，按 "---" 围栏取 `key:` 前缀。
"""

import re

from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent / ".agents" / "skills" / "learning-factory"
SKILL_MD = SKILL_DIR / "SKILL.md"

# 五级中文标题（SKILL.md 与 progressive-learning.md 必须同时包含，防一处改动漂移）
FIVE_LEVEL_TITLES = ["概览与动机", "安装与 Hello World", "核心概念", "实战模式", "进阶方向"]

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


def test_references_exist():
    """SKILL.md 与各角色卡中的相对路径引用（references/、scripts/、templates/）
    必须在 skill 目录下真实存在——skill 分发后无法靠仓库其他文件兜底。"""
    docs = [SKILL_MD, *sorted((SKILL_DIR / "references").glob("*.md"))]
    pattern = re.compile(r"(?:references|scripts|templates)/[A-Za-z0-9_][A-Za-z0-9_./-]*")
    missing = []
    for doc in docs:
        for ref in set(pattern.findall(doc.read_text(encoding="utf-8"))):
            # 去掉命令占位（如 scripts/build_html.py 后面拼接的 <dir>）与行内代码围栏
            ref = ref.rstrip("./")
            if not (SKILL_DIR / ref).exists():
                missing.append(f"{doc.name} → {ref}")
    assert missing == [], "引用了不存在的文件:\n" + "\n".join(missing)


def test_artifact_names_consistent(build_html_module):
    """SKILL.md 列出的产物名与脚本 ARTIFACT_NAMES 完全一致（单一事实源，
    spec §6.5）：一处改动另一处必须跟着改，测试防漂移。
    目录树代码块是产物规范的权威位置，必须逐一列出全部产物名。"""
    skill_md = SKILL_MD.read_text(encoding="utf-8")
    artifacts = set(build_html_module.ARTIFACT_NAMES)
    assert artifacts == {"README.md", "learning-path.md", "resources.md", "code-examples"}
    # 目录树代码块（Output Format 下第一个 ``` 围栏）
    tree_match = re.search(r"```\n(Learning-Factory[\s\S]*?)```", skill_md)
    assert tree_match, "SKILL.md 缺目录树代码块"
    for name in build_html_module.ARTIFACT_NAMES:
        assert name in tree_match.group(1), f"SKILL.md 目录树缺产物名 {name}"


def test_five_level_titles_consistent():
    """五级中文标题同时出现在 SKILL.md 与 progressive-learning.md。"""
    progressive = (SKILL_DIR / "references" / "progressive-learning.md").read_text(encoding="utf-8")
    skill_md = SKILL_MD.read_text(encoding="utf-8")
    for title in FIVE_LEVEL_TITLES:
        assert title in skill_md, f"SKILL.md 缺五级标题 {title}"
        assert title in progressive, f"progressive-learning.md 缺五级标题 {title}"

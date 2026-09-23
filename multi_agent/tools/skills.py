"""
tools/skills.py
Skill 渐进披露加载工具：系统提示词只注入技能清单（name + description），
模型运行时匹配到任务后通过 load_skill 工具按需拉取 SKILL.md 全文，
references 参考文件再深一层按需加载——避免技能全文常驻每轮请求的上下文。
"""

from pathlib import Path

import os

# Skill 根目录（项目根 skills/；2026-09-23 由 .claude/skills 迁出——独立 CLI 发布
# 不借用 Claude Code 的目录约定，避免外部用户认知混淆）
SKILLS_DIR = Path(__file__).parent.parent / "skills"


def get_output_root_dir() -> str:
    """
    技能产物输出根目录：环境变量 MULTI_AGENT_OUTPUT_DIR 可覆盖（CLI
    --output-dir 的落地通道），默认 Learning-Factory。

    enforcement、兜底文案与技能文本（load_skill）三处共用此取值，
    保证模型在任一通道看到的目录指示一致。
    """
    return os.environ.get("MULTI_AGENT_OUTPUT_DIR", "Learning-Factory")


def _apply_output_root(text: str) -> str:
    """自定义输出根目录时替换技能文本中的默认目录（与 enforcement 注入一致）。"""
    root = get_output_root_dir()
    if root != "Learning-Factory":
        return text.replace("Learning-Factory", root)
    return text


def _parse_frontmatter(text: str) -> dict:
    """
    解析 SKILL.md 头部的 YAML frontmatter（--- 包围的 key: value 行）。

    只提取 name / description 两个简单键（单行值），不引第三方 YAML 库。
    无 frontmatter 时返回空 dict。
    """
    if not text.startswith("---"):
        return {}
    result = {}
    for line in text.splitlines()[1:]:
        if line.strip() == "---":
            break
        for key in ("name", "description"):
            prefix = key + ":"
            if line.startswith(prefix):
                result[key] = line[len(prefix):].strip()
    return result


def get_skill_manifest() -> list:
    """
    扫描 SKILLS_DIR，返回全部技能的清单（渐进披露第一层）。

    每项形如 {"name": str, "description": str}，供 load_skills() 拼接
    system prompt 中的技能清单。frontmatter 缺失时 name 回退为目录名、
    description 回退为空串。
    """
    manifest = []
    if not SKILLS_DIR.exists():
        return manifest
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue
        meta = _parse_frontmatter(skill_file.read_text(encoding="utf-8"))
        manifest.append({
            "name": meta.get("name", skill_dir.name),
            "description": meta.get("description", ""),
        })
    return manifest


def _list_reference_files(skill_dir: Path) -> list:
    """列出技能目录下 references/ 中的 .md 文件名（无则空列表）。"""
    refs_dir = skill_dir / "references"
    if not refs_dir.exists():
        return []
    return sorted(p.name for p in refs_dir.iterdir() if p.suffix == ".md")


def _find_skill_dir(skill_name: str):
    """
    按名定位技能目录：同时接受目录名与 frontmatter name（两者通常一致）。

    返回:
        技能目录 Path；找不到返回 None。
    """
    if not SKILLS_DIR.exists():
        return None
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue
        meta = _parse_frontmatter(skill_file.read_text(encoding="utf-8"))
        if skill_name in (skill_dir.name, meta.get("name")):
            return skill_dir
    return None


async def load_skill(skill_name: str, reference: str = None) -> str:
    """
    按需加载技能内容（渐进披露第二/三层）。

    参数:
        skill_name: 技能名（清单中的 name）
        reference:  可选，references/ 下的 .md 文件名；指定时返回该参考文件全文

    返回:
        SKILL.md 全文（尾部附参考文件清单与加载指引）、参考文件全文、或错误串
    """
    skill_dir = _find_skill_dir(skill_name)
    if skill_dir is None:
        names = [item["name"] for item in get_skill_manifest()]
        return f"[错误] 未知技能: {skill_name}（可用: {', '.join(names) or '无'}）"

    # 第三层：指定 reference 时返回参考文件全文
    if reference is not None:
        ref_file = skill_dir / "references" / reference
        if not ref_file.exists() or ref_file.suffix != ".md":
            available = _list_reference_files(skill_dir)
            return f"[错误] 未知参考文件: {reference}（可用: {', '.join(available) or '无'}）"
        return _apply_output_root(ref_file.read_text(encoding="utf-8").strip())

    # 第二层：返回 SKILL.md 全文 + 参考文件指引
    content = (skill_dir / "SKILL.md").read_text(encoding="utf-8").strip()
    refs = _list_reference_files(skill_dir)
    if refs:
        content += (
            "\n\n---\n\n"
            "# 可按需加载的参考文件（用 load_skill 的 reference 参数读取）：\n"
            + "\n".join(f"- {name}" for name in refs)
        )
    return _apply_output_root(content)


# ── Tool Schema ────────────────────────────────────────────────────────────────

SKILL_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "load_skill",
        "description": (
            "加载一个技能的完整工作流定义（SKILL.md）。当用户请求与技能清单中"
            "某个技能的描述匹配时，必须先调用本工具获取完整工作流，再严格遵循执行。"
            "技能正文中提到的 references/ 参考文件用 reference 参数按需加载。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "技能名（技能清单中列出的 name）",
                },
                "reference": {
                    "type": "string",
                    "description": "可选：references/ 下的 .md 文件名，指定时返回该参考文件全文",
                },
            },
            "required": ["skill_name"],
        },
    },
}

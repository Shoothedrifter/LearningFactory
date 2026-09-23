"""
tests/test_progressive_disclosure.py
load_skills 渐进披露重构与 load_skill 工具管线接通的 TDD 测试。
"""

from learning_factory.tools import skills as skills_mod
from helpers import make_tool_call, make_tool_calls_response, make_text_response
from learning_factory.tools import SKILL_TOOL_SCHEMA

from learning_factory import agent


def _make_skill(root, name, description="测试技能", body="# 技能正文 MARKER"):
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n{body}", encoding="utf-8"
    )


def test_load_skills_injects_manifest_not_body(tmp_path, monkeypatch):
    """清单注入：含 name/description 与 load_skill 指引；不含技能正文（第一层不泄露第二层）。"""
    monkeypatch.setattr(skills_mod, "SKILLS_DIR", tmp_path)
    _make_skill(tmp_path, "my-skill", description="做某事")
    text = agent.load_skills()
    assert "my-skill" in text and "做某事" in text
    assert "load_skill" in text   # 指引模型按需加载
    assert "MARKER" not in text   # 技能正文不进入 system prompt
    assert len(text) < 2000       # 轻量清单（旧全文注入约 4.6KB，此上限防机制回退）


def test_load_skills_empty_when_no_skills(tmp_path, monkeypatch):
    monkeypatch.setattr(skills_mod, "SKILLS_DIR", tmp_path / "不存在")
    assert agent.load_skills() == ""


def test_skill_tool_visible_to_main_agent():
    """load_skill 的 schema 必须在主 Agent 工具列表中（模型才能调用到）。"""
    assert SKILL_TOOL_SCHEMA in agent.MAIN_AGENT_TOOLS


async def test_main_agent_pipeline_executes_load_skill(patch_openai, monkeypatch, tmp_path):
    """端到端管线：主 Agent 发出 load_skill 调用 → 真实执行（读磁盘）→ 结果回填 tool 消息。"""
    monkeypatch.setattr(skills_mod, "SKILLS_DIR", tmp_path)
    _make_skill(tmp_path, "my-skill", body="# 真实技能工作流")

    client = patch_openai(
        make_tool_calls_response([make_tool_call("c1", "load_skill", skill_name="my-skill")]),
        make_text_response("已按技能完成"),
    )

    answer = await agent.run_main_agent(
        system_prompt="测试",
        messages=[{"role": "user", "content": "学一个工具"}],
        sub_prompts={},
    )

    assert answer == "已按技能完成"
    tool_msg = client.chat.completions.create.call_args_list[1].kwargs["messages"][3]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "c1"
    assert "真实技能工作流" in tool_msg["content"]  # load_skill 真实读到了文件


def test_enforcement_directs_file_writer_and_parallel_dispatch(tmp_path, monkeypatch):
    """enforcement 必须包含：dispatch file_writer 指示（P3 后主 Agent 无写入工具）+ 并行 dispatch 指示。"""
    monkeypatch.setattr(skills_mod, "SKILLS_DIR", tmp_path)
    _make_skill(tmp_path, "my-skill", description="做某事")
    text = agent.load_skills()
    assert "NO file-writing tools" in text  # P3：主 Agent 无写入工具，写入统一 dispatch
    assert "file_writer" in text            # dispatch 指示指向专职写入引擎
    assert "SAME round" in text             # 并行指示：不同文件的 dispatch 同轮发起
    assert "across turns" in text           # 跨轮续写条款：产物目录跨轮不变
    assert "full relative paths" in text    # F1：正常完成的最终答案也须引用完整路径
    assert "list_directory" in text         # 续写前先列目录确认既有产物
    assert len(text) < 2000                 # 清单层仍保持轻量

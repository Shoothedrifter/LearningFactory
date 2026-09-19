"""
agents/subagents.py
四个子 Agent 的定义和入口函数。

每个子 Agent 都是对 run_agent() 的一次封装，区别只在于：
  - 使用的系统提示词（从 prompts/ 目录加载，与原项目完全一致）
  - 可用的工具集合
  - 使用的模型
"""

from typing import AsyncGenerator

from agents.base import run_agent, run_agent_stream
from tools import FILESYSTEM_TOOL_SCHEMAS, WEB_TOOL_SCHEMAS, REPO_TOOL_SCHEMAS

# 子 Agent 使用更快更便宜的模型
# glm-5-turbo 速度快、成本低，适合执行具体的搜索/分析任务
_SUB_AGENT_MODEL = "glm-5-turbo"


# ── docs_researcher ────────────────────────────────────────────────────────────

async def run_docs_researcher(task: str, prompt: str) -> str:
    """
    文档研究员：从官方文档中查找和提取信息。
    工具：WebSearch + WebFetch
    
    参数:
        task:   主 Agent 分配的具体任务描述
        prompt: 从 prompts/docs_researcher.md 加载的系统提示词
    """
    print(f"\n[docs_researcher] 开始任务: {task[:80]}...")
    result = await run_agent(
        system_prompt=prompt,
        tool_schemas=WEB_TOOL_SCHEMAS,          # 只能搜索和抓取网页
        messages=[{"role": "user", "content": task}],
        model=_SUB_AGENT_MODEL,
        agent_name="docs_researcher",
    )
    return result


# ── repo_analyzer ──────────────────────────────────────────────────────────────

async def run_repo_analyzer(task: str, prompt: str) -> str:
    """
    代码仓库分析员：分析代码库结构、示例和实现细节。
    工具：WebSearch + GitHub 仓库工具（repo_structure / repo_read_file / repo_search）

    注意：repo_analyzer 使用 glm-5（而非 glm-5-turbo），
    因为仓库分析需要可靠地调用多个工具并组合结果。

    参数:
        task:   主 Agent 分配的具体任务描述
        prompt: 从 prompts/repo_analyzer.md 加载的系统提示词
    """
    print(f"\n[repo_analyzer] 开始任务: {task[:80]}...")
    result = await run_agent(
        system_prompt=prompt,
        tool_schemas=WEB_TOOL_SCHEMAS + REPO_TOOL_SCHEMAS,  # 搜索 + GitHub 仓库工具
        messages=[{"role": "user", "content": task}],
        model="glm-5",  # 仓库分析需要更强的模型来可靠调用工具
        agent_name="repo_analyzer",
        max_rounds=15,  # 仓库分析通常需要多轮探索，给予更多轮次
    )
    return result


# ── web_researcher ─────────────────────────────────────────────────────────────

async def run_web_researcher(task: str, prompt: str) -> str:
    """
    网络研究员：查找文章、视频和社区内容。
    工具：WebSearch + WebFetch
    
    参数:
        task:   主 Agent 分配的具体任务描述
        prompt: 从 prompts/web_researcher.md 加载的系统提示词
    """
    print(f"\n[web_researcher] 开始任务: {task[:80]}...")
    result = await run_agent(
        system_prompt=prompt,
        tool_schemas=WEB_TOOL_SCHEMAS,
        messages=[{"role": "user", "content": task}],
        model=_SUB_AGENT_MODEL,
        agent_name="web_researcher",
    )
    return result


# ── file_writer ────────────────────────────────────────────────────────────────

# 写入轮次预算：长文档 8-10 块 + 读现状 + 写后验证 + 转义试错余量
# （2026-09-19 P3：主 Agent 移除直接写入工具后，长文档写入统一走本引擎）
_FILE_WRITER_MAX_ROUNDS = 30


async def run_file_writer(task: str, prompt: str) -> str:
    """
    文件写入引擎：把任务描述的内容分块写入目标文件（P3）。

    工具：write_file + append_file + read_file + list_directory（完整文件系统工具集）
    工作流承载在 prompts/file_writer.md：分块 ≤1400、先读后写、写后验证、
    确定性摘要（只认工具结果）。

    参数:
        task:   主 Agent 分配的写入任务（目标文件完整相对路径 + 内容要求/要点）
        prompt: 从 prompts/file_writer.md 加载的系统提示词
    """
    print(f"\n[file_writer] 开始任务: {task[:80]}...")
    result = await run_agent(
        system_prompt=prompt,
        tool_schemas=FILESYSTEM_TOOL_SCHEMAS,  # 写入引擎独享完整文件系统工具
        messages=[{"role": "user", "content": task}],
        model=_SUB_AGENT_MODEL,
        agent_name="file_writer",
        max_rounds=_FILE_WRITER_MAX_ROUNDS,
    )
    return result


# ── 子 Agent 调度表 ────────────────────────────────────────────────────────────
# 主 Agent 通过这张表把 agent_name 映射到对应的函数
# 注意：每个函数还需要 prompt 参数，在 agent.py 中注入

SUBAGENT_RUNNERS = {
    "docs_researcher": run_docs_researcher,
    "repo_analyzer": run_repo_analyzer,
    "web_researcher": run_web_researcher,
    "file_writer": run_file_writer,
}


# ── 子 Agent 流式版本 ──────────────────────────────────────────────────────────


async def run_docs_researcher_stream(task: str, prompt: str) -> AsyncGenerator[str, None]:
    """docs_researcher 的流式版本。

    注意：subagent start/done 事件由主 Agent 调度层（agent.py 的
    _run_tool_call_streaming）统一发送；本函数只转发内部执行过程事件，
    避免前端收到重复的事件对。
    """
    async for event in run_agent_stream(
        system_prompt=prompt,
        tool_schemas=WEB_TOOL_SCHEMAS,
        messages=[{"role": "user", "content": task}],
        model=_SUB_AGENT_MODEL,
        agent_name="docs_researcher",
    ):
        yield event


async def run_repo_analyzer_stream(task: str, prompt: str) -> AsyncGenerator[str, None]:
    """repo_analyzer 的流式版本。

    注意：subagent start/done 事件由主 Agent 调度层（agent.py 的
    _run_tool_call_streaming）统一发送；本函数只转发内部执行过程事件，
    避免前端收到重复的事件对。
    """
    async for event in run_agent_stream(
        system_prompt=prompt,
        tool_schemas=WEB_TOOL_SCHEMAS + REPO_TOOL_SCHEMAS,
        messages=[{"role": "user", "content": task}],
        model="glm-5",
        agent_name="repo_analyzer",
        max_rounds=15,
    ):
        yield event


async def run_web_researcher_stream(task: str, prompt: str) -> AsyncGenerator[str, None]:
    """web_researcher 的流式版本。

    注意：subagent start/done 事件由主 Agent 调度层（agent.py 的
    _run_tool_call_streaming）统一发送；本函数只转发内部执行过程事件，
    避免前端收到重复的事件对。
    """
    async for event in run_agent_stream(
        system_prompt=prompt,
        tool_schemas=WEB_TOOL_SCHEMAS,
        messages=[{"role": "user", "content": task}],
        model=_SUB_AGENT_MODEL,
        agent_name="web_researcher",
    ):
        yield event


async def run_file_writer_stream(task: str, prompt: str) -> AsyncGenerator[str, None]:
    """file_writer 的流式版本（事件责任归主 Agent 调度层，本函数只转发内部过程事件）。"""
    async for event in run_agent_stream(
        system_prompt=prompt,
        tool_schemas=FILESYSTEM_TOOL_SCHEMAS,
        messages=[{"role": "user", "content": task}],
        model=_SUB_AGENT_MODEL,
        agent_name="file_writer",
        max_rounds=_FILE_WRITER_MAX_ROUNDS,
    ):
        yield event


# 流式版本的子 Agent 调度表
SUBAGENT_STREAM_RUNNERS = {
    "docs_researcher": run_docs_researcher_stream,
    "repo_analyzer": run_repo_analyzer_stream,
    "web_researcher": run_web_researcher_stream,
    "file_writer": run_file_writer_stream,
}

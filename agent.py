"""
agent.py
主入口：对话循环 + 主 Agent 定义。

与原版 agent.py 的对应关系：
  原版 ClaudeSDKClient     → 本文件的 main() 对话循环
  原版 ClaudeAgentOptions  → 本文件的 MAIN_AGENT_TOOLS + run_agent()
  原版 AgentDefinition     → agents/subagents.py 中各个 run_* 函数
  原版 MCP notion 服务器   → tools/notion.py 直接调用 Notion REST API
"""

import asyncio
import json
import os
from pathlib import Path
from typing import AsyncGenerator

from dotenv import load_dotenv

from agents.base import run_agent
from agents.subagents import SUBAGENT_RUNNERS, SUBAGENT_STREAM_RUNNERS
from tools import NOTION_TOOL_SCHEMAS, WEB_TOOL_SCHEMAS, FILESYSTEM_TOOL_SCHEMAS, TOOL_REGISTRY

# 加载 .env 文件中的环境变量
load_dotenv()

# ── Prompt 加载 ────────────────────────────────────────────────────────────────

PROMPTS_DIR = "prompts"

def load_prompt(filename: str) -> str:
    """从 prompts/ 目录加载提示词文件（与原项目完全一致）。"""
    with open(f"{PROMPTS_DIR}/{filename}", "r", encoding="utf-8") as f:
        return f.read().strip()


SKILLS_DIR = Path(__file__).parent / ".claude" / "skills"


def load_skills() -> str:
    """
    从 .claude/skills/ 目录加载所有 Skill，格式化为可注入 system prompt 的文本。

    每个 Skill 目录结构：
        .claude/skills/{skill-name}/
        ├── SKILL.md                  ← 主定义文件（必须存在）
        └── references/*.md           ← 参考文件（可选）

    返回:
        拼接好的 Skill 文本；如果没有 Skill 则返回空字符串。
    """
    if not SKILLS_DIR.exists():
        return ""

    parts: list[str] = []

    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue

        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue

        content = skill_file.read_text(encoding="utf-8").strip()
        parts.append(content)

        # 加载 references/ 下的参考文件
        refs_dir = skill_dir / "references"
        if refs_dir.exists():
            for ref_file in sorted(refs_dir.iterdir()):
                if ref_file.suffix == ".md":
                    ref_content = ref_file.read_text(encoding="utf-8").strip()
                    parts.append(
                        f"\n\n---\n\n# Reference: {ref_file.name}\n\n{ref_content}"
                    )

    if not parts:
        return ""

    skills_text = "\n\n---\n\n".join(parts)

    # 注入强制执行规则，确保主 Agent 严格遵循 Skill 工作流
    enforcement = """

## Skill Execution Rules (MANDATORY)

When a Skill matches the user's request, you MUST follow these rules without exception:

### Research Phase
- You MUST dispatch ALL THREE subagents in a single round (parallel dispatch):
  - `docs_researcher` → official documentation
  - `repo_analyzer` → repository structure and code
  - `web_researcher` → community content (tutorials, videos, discussions)
- Do NOT skip any subagent. Do NOT proceed with only one or two.
- Include the Skill's extraction instructions in each subagent's task description.

### Structure Phase
- After receiving ALL subagent results, organize content strictly according to the Skill's structure requirements.
- Do NOT invent your own structure. Follow the reference file's levels exactly.

### Output Phase
- You MUST use `write_file` tool to create local files. Do NOT use Notion for Skill output.
- Create the exact folder structure defined by the Skill (e.g. `learning-{tool-name}/`).
- Write each required file individually using `write_file`.
- After writing all files, use `list_directory` to confirm the output is correct.
"""

    return "\n\n## Available Skills\n\n" + skills_text + enforcement


# ── 主 Agent 工具定义 ──────────────────────────────────────────────────────────
#
# 主 Agent 拥有两类工具：
#   1. dispatch_to_subagent：把子任务分派给专门的子 Agent
#   2. Notion 工具：直接读写 Notion（对应原版 allowed_tools 中的 notion MCP 工具）
#
# 注意：主 Agent 没有 Bash/Repo 工具，这些能力通过子 Agent 间接使用。
# （与原版设计一致：主 Agent 负责协调，子 Agent 负责执行）

DISPATCH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "dispatch_to_subagent",
        "description": (
            "把一个具体的子任务分派给专门的子 Agent 执行，并获取结果。\n"
            "子 Agent 说明：\n"
            "  - docs_researcher：从官方文档中查找信息\n"
            "  - repo_analyzer：分析代码仓库结构和实现细节\n"
            "  - web_researcher：搜索文章、视频、社区讨论等内容"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "enum": ["docs_researcher", "repo_analyzer", "web_researcher"],
                    "description": "要调用的子 Agent 名称",
                },
                "task": {
                    "type": "string",
                    "description": "给子 Agent 的具体任务描述，越详细越好",
                },
            },
            "required": ["agent_name", "task"],
        },
    },
}

# 主 Agent 的完整工具列表：调度子 Agent + Notion 读写 + 本地文件写入 + 网页搜索
MAIN_AGENT_TOOLS = [DISPATCH_TOOL_SCHEMA] + NOTION_TOOL_SCHEMAS + FILESYSTEM_TOOL_SCHEMAS + WEB_TOOL_SCHEMAS

# 主 Agent 使用能力最强的模型
MAIN_AGENT_MODEL = "glm-4-plus"


# ── 工具执行器扩展 ─────────────────────────────────────────────────────────────
#
# agents/base.py 中的 TOOL_REGISTRY 只包含普通工具（web/bash/notion）。
# dispatch_to_subagent 是特殊工具，需要访问 prompt，所以在这里单独处理。

async def execute_dispatch(agent_name: str, task: str, sub_prompts: dict) -> str:
    """
    执行 dispatch_to_subagent 工具调用。
    
    参数:
        agent_name:  目标子 Agent 名称
        task:        任务描述
        sub_prompts: 各子 Agent 的提示词字典 {"docs_researcher": "...", ...}
    """
    runner = SUBAGENT_RUNNERS.get(agent_name)
    if runner is None:
        return f"[错误] 未知子 Agent: {agent_name}"
    
    prompt = sub_prompts.get(agent_name, "你是一个有帮助的助手。")
    return await runner(task=task, prompt=prompt)


async def _run_plain_tool(fn_name: str, fn_args: dict) -> str:
    """
    执行 TOOL_REGISTRY 中的普通工具（dispatch_to_subagent 不走这里）。
    普通版与流式版的主 Agent Loop 共用此实现，保证错误处理行为一致。
    """
    try:
        if fn_name in TOOL_REGISTRY:
            return str(await TOOL_REGISTRY[fn_name](**fn_args))
        return f"[错误] 未知工具: {fn_name}"
    except Exception as e:
        return f"[错误] 工具执行失败 ({fn_name}): {e}"


async def _execute_tool_call(tool_call, sub_prompts: dict) -> str:
    """
    执行单个工具调用（dispatch_to_subagent 或 TOOL_REGISTRY 中的普通工具）。

    始终返回字符串结果、不向外抛异常（含参数解析失败、未知工具/执行异常），
    以便 asyncio.gather 并发调用时单个失败不影响其他调用。
    """
    fn_name = tool_call.function.name
    fn_args_raw = tool_call.function.arguments

    print(f"  → {fn_name}({fn_args_raw[:80]}{'...' if len(fn_args_raw) > 80 else ''})")
    try:
        fn_args = json.loads(fn_args_raw)
        if fn_name == "dispatch_to_subagent":
            result = await execute_dispatch(
                agent_name=fn_args["agent_name"],
                task=fn_args["task"],
                sub_prompts=sub_prompts,
            )
        else:
            result = await _run_plain_tool(fn_name, fn_args)  # 内部自带异常捕获
    except json.JSONDecodeError:
        result = f"[错误] 工具参数解析失败: {fn_args_raw}"
    except Exception as e:
        result = f"[错误] 工具执行失败 ({fn_name}): {e}"
    print(f"  ← 结果: {str(result)[:120]}{'...' if len(str(result)) > 120 else ''}")
    return str(result)


# ── 主 Agent Loop（带 dispatch 支持）─────────────────────────────────────────

async def run_main_agent(
    system_prompt: str,
    messages: list,
    sub_prompts: dict,
    model: str = MAIN_AGENT_MODEL,
) -> str:
    """
    主 Agent Loop，在 base.run_agent 基础上增加对 dispatch_to_subagent 的处理。
    其余工具（notion/web）直接走 TOOL_REGISTRY。
    """
    import openai
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=os.environ.get("GLM_API_KEY", ""),
        base_url="https://open.bigmodel.cn/api/paas/v4/",
    )

    local_messages = list(messages)
    MAX_ROUNDS = 15

    for round_num in range(1, MAX_ROUNDS + 1):
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system_prompt}] + local_messages,
            tools=MAIN_AGENT_TOOLS,
            tool_choice="auto",
        )

        choice = response.choices[0]
        msg = choice.message
        finish_reason = choice.finish_reason

        if finish_reason == "tool_calls" and msg.tool_calls:
            print(f"\n[主 Agent] 第 {round_num} 轮，调用 {len(msg.tool_calls)} 个工具...")

            local_messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })

            # 同一轮的多个工具调用并发执行（dispatch 到多个子 Agent 时即真正的并行）
            # 注意：并行时各调用的 print 日志会交错输出，属预期行为
            results = await asyncio.gather(
                *(_execute_tool_call(tc, sub_prompts) for tc in msg.tool_calls)
            )

            # gather 保持结果顺序与 tool_calls 一致，按协议顺序回填 tool 消息
            for tool_call, result in zip(msg.tool_calls, results):
                local_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })
        else:
            # 无工具调用，返回最终答案
            print(f"\n[主 Agent] 完成（共 {round_num} 轮）")
            return msg.content or ""

    return msg.content or "[达到最大调用轮次]"


# ── 主 Agent Loop 流式版本 ──────────────────────────────────────────────────────

def _sse(event_type: str, **kwargs) -> str:
    """构造 SSE 事件 JSON。"""
    return json.dumps({"type": event_type, **kwargs}, ensure_ascii=False)


async def run_main_agent_stream(
    system_prompt: str,
    messages: list,
    sub_prompts: dict,
    model: str = MAIN_AGENT_MODEL,
) -> AsyncGenerator[str, None]:
    """
    主 Agent 的流式版本：通过 yield 推送 SSE 事件。

    事件类型:
        status    — 状态更新
        tool_call — 工具调用详情
        subagent  — 子 Agent 开始/完成
        answer    — 最终答案
    """
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=os.environ.get("GLM_API_KEY", ""),
        base_url="https://open.bigmodel.cn/api/paas/v4/",
    )

    local_messages = list(messages)
    MAX_ROUNDS = 15

    yield _sse("status", agent="main", message="开始处理...")

    for round_num in range(1, MAX_ROUNDS + 1):
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system_prompt}] + local_messages,
            tools=MAIN_AGENT_TOOLS,
            tool_choice="auto",
        )

        choice = response.choices[0]
        msg = choice.message
        finish_reason = choice.finish_reason

        if finish_reason == "tool_calls" and msg.tool_calls:
            yield _sse(
                "status", agent="main",
                message=f"第 {round_num} 轮，调用 {len(msg.tool_calls)} 个工具...",
            )

            local_messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })

            # ── 并行执行本轮所有工具调用，过程事件经共享队列实时转发 ──
            event_queue: asyncio.Queue = asyncio.Queue()

            async def _run_tool_call_streaming(tool_call) -> str:
                """执行单个工具调用，把过程事件推入 event_queue，返回工具结果字符串。"""
                fn_name = tool_call.function.name

                if fn_name == "dispatch_to_subagent":
                    # 子 Agent 调度 — 并行时多个子 Agent 的事件会交错，事件内带名称可区分
                    try:
                        fn_args = json.loads(tool_call.function.arguments)
                        sub_name = fn_args["agent_name"]
                        sub_task = fn_args["task"]
                    except (json.JSONDecodeError, KeyError) as e:
                        return f"[错误] dispatch_to_subagent 参数无效: {e}"

                    await event_queue.put(
                        _sse("subagent", subagent=sub_name, status="start", task=sub_task[:100])
                    )

                    sub_runner = SUBAGENT_STREAM_RUNNERS.get(sub_name)
                    sub_prompt = sub_prompts.get(sub_name, "你是一个有帮助的助手。")

                    if sub_runner is None:
                        result = f"[错误] 未知子 Agent: {sub_name}"
                    else:
                        sub_results = []
                        try:
                            # 消费子 Agent 事件流；单个子 Agent 崩溃只影响自身结果
                            async for sub_event_str in sub_runner(task=sub_task, prompt=sub_prompt):
                                await event_queue.put(sub_event_str)  # 实时转发
                                try:
                                    sub_event = json.loads(sub_event_str)
                                    if sub_event.get("type") == "answer":
                                        sub_results.append(sub_event.get("content", ""))
                                except (json.JSONDecodeError, AttributeError):
                                    pass
                        except Exception as e:
                            result = f"[错误] 工具执行失败 ({fn_name}): {e}"
                        else:
                            result = "\n".join(sub_results) if sub_results else "[子 Agent 未返回结果]"

                    await event_queue.put(_sse("subagent", subagent=sub_name, status="done"))
                    return result
                else:
                    # 普通工具（与普通版共用 _run_plain_tool）
                    try:
                        fn_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError as e:
                        return f"[错误] 工具参数解析失败: {e}"
                    await event_queue.put(
                        _sse("tool_call", agent="main", tool=fn_name,
                             args=str(fn_args)[:200], status="calling")
                    )
                    result = await _run_plain_tool(fn_name, fn_args)
                    await event_queue.put(
                        _sse("tool_call", agent="main", tool=fn_name,
                             args=str(fn_args)[:200],
                             result=str(result)[:300], status="done")
                    )
                    return result

            gather_future = asyncio.gather(
                *(_run_tool_call_streaming(tc) for tc in msg.tool_calls)
            )

            # 泵：所有任务完成且队列排空前，持续把事件 yield 给调用方（50ms 轮询）
            while not (gather_future.done() and event_queue.empty()):
                try:
                    yield await asyncio.wait_for(event_queue.get(), timeout=0.05)
                except asyncio.TimeoutError:
                    continue

            # gather 保持结果顺序与 tool_calls 一致，按协议顺序回填 tool 消息
            results = await gather_future
            for tool_call, result in zip(msg.tool_calls, results):
                local_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })
        else:
            final_answer = msg.content or ""
            yield _sse("status", agent="main", message=f"完成（共 {round_num} 轮）")
            yield _sse("answer", agent="main", content=final_answer)
            return

    # 超出最大轮次
    yield _sse("status", agent="main", message="达到最大轮次，请求模型总结...")
    summary_response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system_prompt}] + local_messages + [
            {"role": "user", "content": "请根据已收集到的信息，整理并输出你的分析结果。不要再调用任何工具，直接给出总结。"},
        ],
        tools=None,
        tool_choice=None,
    )
    summary = summary_response.choices[0].message.content or "[达到最大调用轮次]"
    yield _sse("answer", agent="main", content=summary)


# ── 对话循环 ───────────────────────────────────────────────────────────────────

async def main():
    # 加载所有提示词（与原版完全一致）
    main_agent_prompt   = load_prompt("main_agent.md")
    sub_prompts = {
        "docs_researcher": load_prompt("docs_researcher.md"),
        "repo_analyzer":   load_prompt("repo_analyzer.md"),
        "web_researcher":  load_prompt("web_researcher.md"),
    }

    # 加载 Skill 并追加到主 Agent 系统提示词
    skills_prompt = load_skills()
    if skills_prompt:
        main_agent_prompt += "\n\n" + skills_prompt
        print(f"[系统] 已加载 Skill 配置")

    # 对话历史（多轮对话在这里积累）
    conversation_history: list[dict] = []

    print("=" * 60)
    print("多智能体系统已启动（glm-4-plus 主Agent / glm-4-flash 子Agent）")
    print("输入 'exit' 退出，输入 'clear' 清空对话历史")
    print("=" * 60)

    while True:
        try:
            user_input = input("\n\033[1mYou\033[0m: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue

        if user_input.lower() == "exit":
            print("再见！")
            break

        if user_input.lower() == "clear":
            conversation_history.clear()
            print("[对话历史已清空]")
            continue

        # 把用户消息加入对话历史
        conversation_history.append({"role": "user", "content": user_input})

        print("\n\033[1mAssistant\033[0m: ", end="", flush=True)

        try:
            # 调用主 Agent，传入完整对话历史
            answer = await run_main_agent(
                system_prompt=main_agent_prompt,
                messages=conversation_history,
                sub_prompts=sub_prompts,
            )
            print(answer)

            # 把 Assistant 的回答加入对话历史（支持多轮）
            conversation_history.append({"role": "assistant", "content": answer})

        except Exception as e:
            error_msg = f"[系统错误] {e}"
            print(error_msg)
            # 出错时从历史中移除刚才加入的用户消息，避免历史损坏
            conversation_history.pop()


if __name__ == "__main__":
    asyncio.run(main())

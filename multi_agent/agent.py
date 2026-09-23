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
import argparse
import json
import os
import re
import weakref
from pathlib import Path
from typing import AsyncGenerator

from openai import RateLimitError
from dotenv import load_dotenv

from .agents.base import run_agent
from .agents.subagents import SUBAGENT_RUNNERS, SUBAGENT_STREAM_RUNNERS
from .tools import NOTION_TOOL_SCHEMAS, WEB_TOOL_SCHEMAS, FILESYSTEM_TOOL_SCHEMAS, TOOL_REGISTRY
from .tools.skills import get_skill_manifest, SKILL_TOOL_SCHEMA, get_output_root_dir

# 加载 .env 文件中的环境变量
load_dotenv()

# ── Prompt 加载 ────────────────────────────────────────────────────────────────

# 包内绝对路径（与 SKILLS_DIR 同构）：pip 安装后在任意 cwd 运行都能读到提示词
PROMPTS_DIR = Path(__file__).parent / "prompts"

def load_prompt(filename: str) -> str:
    """从包内 prompts/ 目录加载提示词文件（cwd 无关，安装后任意目录可用）。"""
    with open(PROMPTS_DIR / filename, "r", encoding="utf-8") as f:
        return f.read().strip()


def load_skills() -> str:
    """
    构建注入 system prompt 的技能清单（渐进披露第一层）。

    只注入各技能 frontmatter 的 name + description 与强制执行规则，
    不注入技能全文——模型匹配到任务后通过 load_skill 工具按需加载
    完整工作流（tools/skills.py），references 参考文件再深一层按需读取。

    注意：技能清单在本函数调用时快照，SKILL.md 正文在 load_skill 调用时实时
    读取——两者读取时机不同属预期设计。
    """
    manifest = get_skill_manifest()
    if not manifest:
        return ""

    # 技能清单：每行 "name: description"（模型据此判断是否匹配用户请求）
    listing = "\n".join(f"- {item['name']}: {item['description']}" for item in manifest)

    # 输出根目录可经环境变量覆盖（CLI --output-dir 通道）；{tool-name} 为
    # 字面占位符，f-string 中需转义为 {{tool-name}}
    output_root = get_output_root_dir()

    enforcement = f"""

## Skill Execution Rules (MANDATORY)

When a user request matches any skill listed above, you MUST:
1. First call `load_skill(skill_name=...)` to load the full workflow, then follow it exactly. When the workflow names a `references/` file as authoritative (e.g. for structure), load it with `load_skill(skill_name=..., reference=...)` BEFORE organizing content.
2. Research Phase: dispatch ALL THREE subagents in a single round (parallel dispatch):
   - `docs_researcher` → official documentation
   - `repo_analyzer` → repository structure and code
   - `web_researcher` → community content (tutorials, videos, discussions)
   Do NOT skip any subagent. Include the Skill's extraction instructions in each task.
3. Output Phase: you have NO file-writing tools. For each output file dispatch
   `file_writer` (one dispatch per file; the task must give the file's full
   relative path under `{output_root}/learning-{{tool-name}}/` plus its content
   requirements and research material in BRIEF form — keep each task short
   (~800 characters); for a long file, dispatch file_writer again to continue
   from its previous summary). Dispatches for different files go in the
   SAME round. Verify afterwards with `read_file` /
   `list_directory`. Skill output MUST stay under
   `{output_root}/learning-{{tool-name}}/` across turns: when continuing
   earlier output, `list_directory` `{output_root}/` first and pass the
   existing file's tail in the file_writer task so it appends rather than
   rewrites; never create a new folder. Do NOT use Notion for Skill output.
   Cite output files with full relative paths in final answers.
"""

    return "\n\n## Available Skills\n\n" + listing + enforcement


# ── 主 Agent 工具定义 ──────────────────────────────────────────────────────────
#
# 主 Agent 拥有两类工具：
#   1. dispatch_to_subagent：把子任务分派给专门的子 Agent
#   2. Notion 工具：直接读写 Notion（对应原版 allowed_tools 中的 notion MCP 工具）
#
# 注意：主 Agent 没有 Bash/Repo 工具，这些能力通过子 Agent 间接使用。
# 注意：主 Agent 也没有写入工具，写入能力由 file_writer 子 Agent 承担（P3）。
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
            "  - web_researcher：搜索文章、视频、社区讨论等内容\n"
            "  - file_writer：把长文档内容分块写入本地文件（专职写入引擎，"
            "主 Agent 自己没有写入工具，所有文件写入都必须分派给它）"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "enum": ["docs_researcher", "repo_analyzer", "web_researcher", "file_writer"],
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

# 主 Agent 的完整工具列表：调度子 Agent + 技能加载 + Notion 读写 + 本地文件读取 + 网页搜索
# 2026-09-19 P3：主 Agent 不再有直接写入工具（实测主模型直写长文档必死循环），
# write_file/append_file 由 file_writer 子 Agent 独享；主 Agent 保留
# read_file/list_directory 用于查验产物。
_MAIN_FS_SCHEMAS = [
    s for s in FILESYSTEM_TOOL_SCHEMAS
    if s["function"]["name"] not in ("write_file", "append_file")
]
MAIN_AGENT_TOOLS = [DISPATCH_TOOL_SCHEMA, SKILL_TOOL_SCHEMA] + NOTION_TOOL_SCHEMAS + _MAIN_FS_SCHEMAS + WEB_TOOL_SCHEMAS

# 主 Agent 使用能力最强的模型
MAIN_AGENT_MODEL = "glm-5"

# 主 Agent 工具调用轮次上限（普通版与流式版共用）
# 模块级常量便于测试中 monkeypatch 缩小轮次来构造耗尽场景
MAX_ROUNDS = 12


def _budget_line(round_num: int) -> str:
    """
    拼接到 system prompt 尾部的轮次预算提示（follow up B）。

    每轮随 round_num 变化、只存在于本次请求的组装层——不写入 local_messages，
    调用方消息与跨会话历史均不受污染；配合 schema 层并行指示（follow up A）
    促使模型把剩余轮次预算花在批量写入上。
    """
    left = MAX_ROUNDS - round_num + 1
    return (
        f"\n\n[Tool-call budget] Round {round_num}/{MAX_ROUNDS}, "
        f"{left} round(s) left including this one — "
        "batch independent tool calls in this round to save budget."
    )


# ── 工具执行器扩展 ─────────────────────────────────────────────────────────────
#
# agents/base.py 中的 TOOL_REGISTRY 只包含普通工具（web/bash/notion）。
# dispatch_to_subagent 是特殊工具，需要访问 prompt，所以在这里单独处理。

# ── dispatch 429 退避重试 ───────────────────────────────────────────────────────
#
# 实测（logs/afterfilewriter.txt，2026-09-21）：并行 dispatch 的启动瞬间并发
# 请求频繁撞 API 速率限制（全程 15+ 次 429），主 Agent 只能消耗轮次逐个补派
# （8 文件任务光补派耗 7 轮）。这里在 dispatch 执行层做一次固定退避重试。
# 已知限制：子 Agent 中途轮次撞 429 时重试会从头重跑任务——研究型子 Agent
# 无副作用；file_writer 的先读后写工作流可缓解大部分场景（接受此权衡，
# 见计划 Ruling 1）。
_DISPATCH_MAX_ATTEMPTS = 2            # 初次 + 1 次重试
_DISPATCH_RETRY_DELAY_SECONDS = 2.0   # 退避时长（测试可 monkeypatch 置 0）

# ── dispatch 并发节流 ──────────────────────────────────────────────────────────
#
# 实测（logs/after_pytorch.txt，2026-09-23）：同轮 8 个 file_writer dispatch 并发
# 启动把账户限流打满（7/8 初次 429），固定退避重试也因各路同步 sleep-重试而
# 11/11 全部用尽；而单 dispatch 补派全部一次成功——限流是并发峰值型，治本
# 需限制同时启动的子 Agent 数。信号量按 event loop 缓存：asyncio.Semaphore
# 在有等待竞争时绑定首个 loop，跨 loop 复用会 RuntimeError（pytest-asyncio
# 每测试新 loop，模块级单例必炸；生产 main() 全程单 loop 不受影响）。
# 附带收益：新 loop 缓存 miss 后读最新常量值，测试 monkeypatch 直接生效。
_DISPATCH_CONCURRENCY_LIMIT = 3  # 同时运行的子 Agent 上限（研究阶段三路并行的语义保持）

_DISPATCH_SEMAPHORES: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = weakref.WeakKeyDictionary()


def _get_dispatch_semaphore() -> asyncio.Semaphore:
    """获取当前 event loop 对应的 dispatch 并发信号量（按 loop 缓存，弱引用防泄漏）。"""
    loop = asyncio.get_running_loop()
    sem = _DISPATCH_SEMAPHORES.get(loop)
    if sem is None:
        sem = asyncio.Semaphore(_DISPATCH_CONCURRENCY_LIMIT)
        _DISPATCH_SEMAPHORES[loop] = sem
    return sem


async def execute_dispatch(agent_name: str, task: str, sub_prompts: dict) -> str:
    """
    执行 dispatch_to_subagent 工具调用。

    撞到 API 速率限制（openai.RateLimitError）时退避重试一次（2026-09-21）；
    重试用尽后照常上抛，交由上层既有 except 回填 [错误] 工具结果。

    参数:
        agent_name:  目标子 Agent 名称
        task:        任务描述
        sub_prompts: 各子 Agent 的提示词字典 {"docs_researcher": "...", ...}
    """
    runner = SUBAGENT_RUNNERS.get(agent_name)
    if runner is None:
        return f"[错误] 未知子 Agent: {agent_name}"

    prompt = sub_prompts.get(agent_name, "你是一个有帮助的助手。")
    # 持槽范围覆盖整个 dispatch（含 429 重试的 sleep）：重试期间占住槽位，
    # 排队的 dispatch 不启动，进一步削平瞬时并发压力
    async with _get_dispatch_semaphore():
        for attempt in range(1, _DISPATCH_MAX_ATTEMPTS + 1):
            try:
                return await runner(task=task, prompt=prompt)
            except RateLimitError:
                if attempt >= _DISPATCH_MAX_ATTEMPTS:
                    raise
                print(f"  → [重试] {agent_name} 撞到速率限制，"
                      f"{_DISPATCH_RETRY_DELAY_SECONDS:.0f} 秒后重试...")
                await asyncio.sleep(_DISPATCH_RETRY_DELAY_SECONDS)


# 工具参数不是合法 JSON 时的错误文案（普通版与流式版共用）
# 设计要点：
#   1. 只回显前 200 字符——全量回显数千字符的原文既占上下文也无助于定位问题
#   2. 附带参数缩短引导——超长参数常因 max_tokens 截断或转义错误而解析失败，
#      引导模型换策略而非以同样方式盲目重试
#      （P3 后主 Agent 无写入工具：超长素材改为分批 dispatch file_writer，
#      不再引导主 Agent 直接分块写入）
MALFORMED_ARGS_MESSAGE = (
    "[错误] 工具参数解析失败（参数前 200 字符）: {raw}\n"
    "提示：超长参数常因截断或转义而无法解析。请把参数大幅缩短后重试："
    "给 dispatch_to_subagent 的 task 只写目标文件路径与内容要点（几百字符），"
    "长内容由 file_writer 子 Agent 自行生成；不要在参数里塞长文本。"
)


def _screen_same_file_writes(tool_calls) -> dict:
    """
    同轮多工具调用的同文件写筛检（确定性防线）。

    enforcement 只是指示，模型可能违反（把同一文件的多个写入/追加块放进
    同一轮）——并发 open("a") 的写入顺序未定义，会导致内容静默颠倒。
    本函数对 write_file/append_file 按 resolved path 去重：同一路径只放行
    第一次出现，其余调用回填拦截错误串（不执行），引导下一轮再追加。

    返回:
        {tool_call 在列表中的索引: 拦截错误串}；无冲突返回空 dict。
    """
    seen: dict = {}  # resolved path → None（利用 dict 有序性做有序集合）
    blocked: dict = {}
    for idx, tc in enumerate(tool_calls):
        if getattr(tc.function, "name", "") not in ("write_file", "append_file"):
            continue
        try:
            path = json.loads(tc.function.arguments).get("path", "")
        except (json.JSONDecodeError, AttributeError):
            continue  # 畸形参数走既有 MALFORMED_ARGS_MESSAGE 路径，不在此拦截
        key = str(Path(path).resolve())
        if key in seen:
            blocked[idx] = (
                "[错误] 同一文件的多个写入/追加块不能放在同一轮（并发追加顺序"
                "未定义，会静默损坏内容）。本轮已执行对该文件的第一个调用，"
                "请把这块放到下一轮再追加。"
            )
        else:
            seen[key] = None
    return blocked


# 从 file_writer 任务文本提取目标文件路径，两级启发式：
#   1) 锚定词（最明确）：文件路径/目标文件/输出文件 + 全/半角冒号后接路径 token
#      （实测新形态见 logs/after_pytorch.txt :218-224，如
#       "文件路径: Learning-Factory/.../01-tensor-basics.py 内容: ..."，无反引号）
#   2) 回退：反引号包裹、形似路径（含 / 或带扩展名）的第一个 token
#      （实测 task 形态见 logs/afterfilewriter.txt，
#       如 "向已有文件 `Learning-Factory/.../learning-path.md` 末尾追加..."）
_TASK_PATH_ANCHOR_PATTERN = re.compile(r"(?:文件路径|目标文件|输出文件)[：:]\s*([^\s，。,；;`]+)")
_TASK_PATH_PATTERN = re.compile(r"`([^`]+)`")


def _extract_dispatch_target_path(task: str):
    """
    从 file_writer 任务文本中启发式提取目标文件路径并归一化。

    提取顺序：锚定词（"文件路径:" 等，显式标注最明确）优先，反引号 token 回退。
    均提取不到返回 None（防线放行，宁放过勿错杀——防误伤无路径 task）。
    """
    for candidate in _TASK_PATH_ANCHOR_PATTERN.findall(task or ""):
        if "/" in candidate or Path(candidate).suffix:
            return str(Path(candidate).resolve())
    for candidate in _TASK_PATH_PATTERN.findall(task or ""):
        if "/" in candidate or Path(candidate).suffix:
            return str(Path(candidate).resolve())
    return None


def _screen_same_file_dispatches(tool_calls) -> dict:
    """
    同轮多 file_writer dispatch 的同文件筛检（确定性防线，2026-09-21）。

    enforcement 的 one-dispatch-per-file 只是指示，实测被违反（同一
    learning-path.md 同轮发 Level 4/Level 5 两个 dispatch，叠加 429 失败
    补派导致全文顺序颠倒）。本函数对 file_writer dispatch 按提取到的
    目标路径去重：同一路径只放行第一次出现，其余回填拦截错误串（不执行），
    引导合并为单任务后下一轮再派。研究型子 Agent 与提取不到路径的
    dispatch 不筛。

    返回:
        {tool_call 在列表中的索引: 拦截错误串}；无冲突返回空 dict。
    """
    seen: dict = {}  # resolved path → None（利用 dict 有序性做有序集合）
    blocked: dict = {}
    for idx, tc in enumerate(tool_calls):
        if getattr(tc.function, "name", "") != "dispatch_to_subagent":
            continue
        try:
            fn_args = json.loads(tc.function.arguments)
        except (json.JSONDecodeError, AttributeError):
            continue  # 畸形参数走既有 MALFORMED_ARGS_MESSAGE 路径，不在此拦截
        if fn_args.get("agent_name") != "file_writer":
            continue
        key = _extract_dispatch_target_path(fn_args.get("task", ""))
        if key is None:
            continue
        if key in seen:
            blocked[idx] = (
                "[错误] 同一轮内有多个 file_writer 任务指向同一文件"
                f"（{key}）：并发写同一文件顺序未定义、会静默损坏内容。"
                "本轮已执行其中第一个任务；请把同一文件的全部内容要求"
                "合并为一个 file_writer 任务，下一轮再派发。"
            )
        else:
            seen[key] = None
    return blocked


async def _blocked_result(result: str, tool_call) -> str:
    """把同轮同文件拦截结果包装成协程并打印日志，便于与真实执行一起 gather。"""
    print(f"  → [拦截] {tool_call.function.name}（同轮同文件，推迟到下一轮）")
    return result


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
        result = MALFORMED_ARGS_MESSAGE.format(raw=fn_args_raw[:200])
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

    for round_num in range(1, MAX_ROUNDS + 1):
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt + _budget_line(round_num)}
            ] + local_messages,
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
            # 同轮同文件写筛检 + 同轮同文件 file_writer dispatch 筛检（两道防线合一；
            # 同一路径只放行第一次出现，同一 tool_call 不可能既带写工具名又是 dispatch）
            blocked = {
                **_screen_same_file_writes(msg.tool_calls),
                **_screen_same_file_dispatches(msg.tool_calls),
            }
            results = await asyncio.gather(*(
                _execute_tool_call(tc, sub_prompts) if i not in blocked
                else _blocked_result(blocked[i], tc)
                for i, tc in enumerate(msg.tool_calls)
            ))

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

    # 达到最大轮次：对齐流式版行为——请求模型基于已有信息总结，而非静默返回占位串
    print(f"\n[主 Agent] 达到最大轮次 ({MAX_ROUNDS})，请求模型总结已有信息...")
    local_messages.append({
        "role": "user",
        "content": f"已达到最大工具调用轮次。请不要再调用任何工具，直接基于以上已获得的全部信息输出最终回答；若学习计划文件只生成了部分，请说明已完成与缺失的文件，路径必须写完整相对路径（含 {get_output_root_dir()}/ 等目录前缀，不得省略），以便后续继续任务时沿用同一目录。已完成与未完成的判定只以工具结果为准：仅工具返回 [成功] 的写入才算已完成，凡工具返回 [错误] 的调用（含被拒绝的写入/追加）一律列为未完成，不得当作已写入。",
    })
    summary_response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system_prompt}] + local_messages,
        tools=None,
        tool_choice=None,
    )
    return summary_response.choices[0].message.content or "[达到最大轮次且总结失败]"


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

    yield _sse("status", agent="main", message="开始处理...")

    for round_num in range(1, MAX_ROUNDS + 1):
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt + _budget_line(round_num)}
            ] + local_messages,
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
                        # 持槽覆盖整个子 Agent 运行（含 429 重试的 sleep），
                        # 与普通版 execute_dispatch 同策略
                        async with _get_dispatch_semaphore():
                            sub_results = []
                            for attempt in range(1, _DISPATCH_MAX_ATTEMPTS + 1):
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
                                except RateLimitError as e:
                                    # 429 退避重试（与 execute_dispatch 同策略）；
                                    # 半程已转发的事件会随重试重复出现，属可接受的日志噪音
                                    if attempt >= _DISPATCH_MAX_ATTEMPTS:
                                        result = f"[错误] 工具执行失败 ({fn_name}): {e}"
                                        break
                                    print(f"  → [重试] {sub_name} 撞到速率限制，"
                                          f"{_DISPATCH_RETRY_DELAY_SECONDS:.0f} 秒后重试...")
                                    await asyncio.sleep(_DISPATCH_RETRY_DELAY_SECONDS)
                                    sub_results = []  # 丢弃半程结果，重新开始
                                    continue
                                except Exception as e:
                                    result = f"[错误] 工具执行失败 ({fn_name}): {e}"
                                    break
                                else:
                                    result = "\n".join(sub_results) if sub_results else "[子 Agent 未返回结果]"
                                    break

                    await event_queue.put(_sse("subagent", subagent=sub_name, status="done"))
                    return result
                else:
                    # 普通工具（与普通版共用 _run_plain_tool）
                    try:
                        fn_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        return MALFORMED_ARGS_MESSAGE.format(
                            raw=tool_call.function.arguments[:200]
                        )
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

            # 同轮同文件写筛检 + 同轮同文件 file_writer dispatch 筛检（两道防线合一；
            # 同一 tool_call 不可能既带写工具名又是 dispatch，两张表键无冲突）
            blocked = {
                **_screen_same_file_writes(msg.tool_calls),
                **_screen_same_file_dispatches(msg.tool_calls),
            }

            async def _run_or_block(index, tc) -> str:
                if index in blocked:
                    await event_queue.put(
                        _sse("tool_call", agent="main", tool=tc.function.name,
                             args="", result=blocked[index][:300], status="done")
                    )
                    return blocked[index]
                return await _run_tool_call_streaming(tc)

            gather_future = asyncio.gather(
                *(_run_or_block(i, tc) for i, tc in enumerate(msg.tool_calls))
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
            {"role": "user", "content": f"请根据已收集到的信息，整理并输出你的分析结果。不要再调用任何工具，直接给出总结；若学习计划文件只生成了部分，请说明已完成与缺失的文件，路径必须写完整相对路径（含 {get_output_root_dir()}/ 等目录前缀，不得省略），以便后续继续任务时沿用同一目录。已完成与未完成的判定只以工具结果为准：仅工具返回 [成功] 的写入才算已完成，凡工具返回 [错误] 的调用（含被拒绝的写入/追加）一律列为未完成，不得当作已写入。"},
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
        "file_writer":     load_prompt("file_writer.md"),  # P3：专职写入引擎
    }

    # 加载 Skill 并追加到主 Agent 系统提示词
    skills_prompt = load_skills()
    if skills_prompt:
        main_agent_prompt += "\n\n" + skills_prompt
        print(f"[系统] 已加载 Skill 配置")

    # 对话历史（多轮对话在这里积累）
    conversation_history: list[dict] = []

    print("=" * 60)
    print("多智能体系统已启动（glm-5 主Agent / glm-5-turbo 子Agent）")
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


def run_cli():
    """
    console_script 入口（pip/pipx 安装后的 multi-agent 命令）。

    解析 CLI 参数后进入异步对话循环；也可用 `python -m multi_agent.agent`
    触发同一入口。--output-dir 经环境变量 MULTI_AGENT_OUTPUT_DIR 落地，
    与 enforcement/兜底文案/技能文本的注入通道共用。
    """
    parser = argparse.ArgumentParser(
        prog="multi-agent",
        description="GLM 多智能体协作研究系统：主 Agent 调度 docs/repo/web/file_writer 四个子 Agent",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="技能产物输出根目录（默认 Learning-Factory；等价环境变量 MULTI_AGENT_OUTPUT_DIR）",
    )
    args = parser.parse_args()
    if args.output_dir:
        os.environ["MULTI_AGENT_OUTPUT_DIR"] = args.output_dir
    asyncio.run(main())


if __name__ == "__main__":
    run_cli()

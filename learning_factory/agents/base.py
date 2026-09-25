"""
agents/base.py
核心 Agent Loop 实现。

这是整个多智能体系统最关键的文件。
它实现了"模型调用 → 工具执行 → 结果回传 → 循环"的标准 ReAct 模式。

为什么不用 LangChain？
  因为这个 loop 本质上只有 30 行逻辑，自己写更透明、更易调试。
"""

import asyncio
import json
import os
from typing import AsyncGenerator
from openai import AsyncOpenAI, RateLimitError
from ..config import get_base_url, get_main_agent_model
from ..tools import TOOL_REGISTRY

# ── GLM 客户端初始化（延迟初始化，避免在 load_dotenv() 之前创建）───────────────
# 智谱 AI (bigmodel.cn) 完全兼容 OpenAI SDK，只需替换 base_url 和 api_key
_glm_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    """延迟初始化 GLM 客户端，确保 load_dotenv() 已经执行过。"""
    global _glm_client
    if _glm_client is None:
        _glm_client = AsyncOpenAI(
            api_key=os.environ.get("LLM_API_KEY", ""),
            base_url=get_base_url(),
        )
    return _glm_client

# ── create 调用的 429 指数退避 ──────────────────────────────────────────────────
# 2026-09-24 docker 实测（logs/docker_.txt）：子 Agent 中途轮次撞 429 时，dispatch
# 层的重试只能从头重跑整个子 Agent（10-40 轮白费）。在 create 调用层原地退避重试
# 可保住已执行的工具轮次；指数序列（2/4/8 秒）用于覆盖账户限流恢复窗口（实测 > 2
# 秒）。用尽后照常冒泡，由 dispatch 层整跑重试兜底（agent.py）。
_CREATE_RETRY_DELAYS = (2.0, 4.0, 8.0)


async def _create_with_backoff(**kwargs):
    """chat.completions.create 的 429 指数退避包装：撞限流原地重试，进度零损失。"""
    for attempt in range(len(_CREATE_RETRY_DELAYS) + 1):
        try:
            return await _get_client().chat.completions.create(**kwargs)
        except RateLimitError:
            if attempt >= len(_CREATE_RETRY_DELAYS):
                raise  # 退避用尽，交上层（dispatch 整跑重试 / 主 Agent 兜底）
            await asyncio.sleep(_CREATE_RETRY_DELAYS[attempt])

# 防止无限循环的最大工具调用轮次
MAX_TOOL_ROUNDS = 10


async def run_agent(
    system_prompt: str,
    tool_schemas: list,
    messages: list,
    model: str | None = None,
    agent_name: str = "Agent",
    max_rounds: int = MAX_TOOL_ROUNDS,
) -> str:
    """
    通用 Agent Loop：持续循环直到模型不再调用工具，返回最终文本答案。

    参数:
        system_prompt:  该 Agent 的系统提示词（定义角色和行为）
        tool_schemas:   该 Agent 可用的工具定义列表（OpenAI function calling 格式）
        messages:       对话历史（[{"role": "user", "content": "..."}, ...]）
        model:          使用的 GLM 模型名称；None 时运行时经 config 层取默认
                        （主 Agent 层 GLM_MAIN_MODEL）
        agent_name:     用于日志输出的 Agent 名称
        max_rounds:     最大工具调用轮次（默认 MAX_TOOL_ROUNDS）

    返回:
        模型最终的文本回答（str）
    """

    # 默认模型延迟到调用时从配置层读取（env 可覆盖，测试可 monkeypatch）
    model = model or get_main_agent_model()

    # 每个 Agent 维护自己的本地消息历史，不污染调用方的 messages
    local_messages = list(messages)

    for round_num in range(1, max_rounds + 1):
        # ── 1. 调用 GLM ──────────────────────────────────────────────────────
        response = await _create_with_backoff(
            model=model,
            messages=[{"role": "system", "content": system_prompt}] + local_messages,
            # 没有工具时传 None，避免 API 报错
            tools=tool_schemas if tool_schemas else None,
            tool_choice="auto" if tool_schemas else None,
        )

        choice = response.choices[0]
        msg = choice.message
        finish_reason = choice.finish_reason

        # ── 2. 判断是否有工具调用 ────────────────────────────────────────────
        if finish_reason == "tool_calls" and msg.tool_calls:
            print(f"  [{agent_name}] 第 {round_num} 轮，调用 {len(msg.tool_calls)} 个工具...")

            # 把模型的这轮回应加入历史（包含 tool_calls 字段）
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

            # 逐个执行工具调用，把结果追加到历史
            for tool_call in msg.tool_calls:
                fn_name = tool_call.function.name
                fn_args_raw = tool_call.function.arguments

                print(f"    → 执行工具: {fn_name}({fn_args_raw[:80]}{'...' if len(fn_args_raw) > 80 else ''})")

                # 执行工具并捕获异常（不让单个工具失败崩溃整个 loop）
                try:
                    fn_args = json.loads(fn_args_raw)
                    tool_fn = TOOL_REGISTRY.get(fn_name)
                    if tool_fn is None:
                        result = f"[错误] 未知工具: {fn_name}"
                    else:
                        result = await tool_fn(**fn_args)
                except json.JSONDecodeError:
                    result = f"[错误] 工具参数解析失败: {fn_args_raw}"
                except TypeError as e:
                    result = f"[错误] 工具参数不匹配: {e}"
                except Exception as e:
                    result = f"[错误] 工具执行异常: {e}"

                print(f"    ← 工具结果: {str(result)[:100]}{'...' if len(str(result)) > 100 else ''}")

                # 把工具结果加入消息历史
                local_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result),
                })

        else:
            # ── 3. 没有工具调用 → 返回最终答案 ──────────────────────────────
            final_answer = msg.content or ""
            print(f"  [{agent_name}] 完成（共 {round_num} 轮）")
            return final_answer

    # 超出最大轮次 → 强制做一次不带工具的总结调用，让模型输出已有发现
    print(f"  [{agent_name}] 达到最大轮次 ({max_rounds})，请求模型总结已有信息...")
    summary_response = await _create_with_backoff(
        model=model,
        messages=[{"role": "system", "content": system_prompt}] + local_messages + [
            {"role": "user", "content": "请根据已收集到的信息，整理并输出你的分析结果。不要再调用任何工具，直接给出总结。"},
        ],
        tools=None,
        tool_choice=None,
    )
    summary = summary_response.choices[0].message.content or "[达到最大调用轮次且无法生成总结]"
    print(f"  [{agent_name}] 已生成总结")
    return summary


# ── 流式版本 ────────────────────────────────────────────────────────────────────


def _sse_event(event_type: str, agent: str, **kwargs) -> str:
    """构造一个 SSE 事件 JSON 字符串。"""
    event = {"type": event_type, "agent": agent, **kwargs}
    return json.dumps(event, ensure_ascii=False)


async def run_agent_stream(
    system_prompt: str,
    tool_schemas: list,
    messages: list,
    model: str | None = None,
    agent_name: str = "Agent",
    max_rounds: int = MAX_TOOL_ROUNDS,
) -> AsyncGenerator[str, None]:
    """
    流式版本的 Agent Loop：通过 yield 推送 SSE 事件。

    model 为 None 时运行时经 config 层取默认（主 Agent 层 GLM_MAIN_MODEL）。

    事件类型:
        status    — 状态更新（开始、轮次等）
        tool_call — 工具调用详情（名称、参数、结果摘要）
        answer    — 最终答案
    """
    # 默认模型延迟到调用时从配置层读取（env 可覆盖，测试可 monkeypatch）
    model = model or get_main_agent_model()
    local_messages = list(messages)

    yield _sse_event("status", agent_name, message="开始处理...")

    for round_num in range(1, max_rounds + 1):
        response = await _create_with_backoff(
            model=model,
            messages=[{"role": "system", "content": system_prompt}] + local_messages,
            tools=tool_schemas if tool_schemas else None,
            tool_choice="auto" if tool_schemas else None,
        )

        choice = response.choices[0]
        msg = choice.message
        finish_reason = choice.finish_reason

        if finish_reason == "tool_calls" and msg.tool_calls:
            yield _sse_event(
                "status", agent_name,
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

            for tool_call in msg.tool_calls:
                fn_name = tool_call.function.name
                fn_args_raw = tool_call.function.arguments

                yield _sse_event(
                    "tool_call", agent_name,
                    tool=fn_name,
                    args=fn_args_raw[:200],
                    status="calling",
                )

                try:
                    fn_args = json.loads(fn_args_raw)
                    tool_fn = TOOL_REGISTRY.get(fn_name)
                    if tool_fn is None:
                        result = f"[错误] 未知工具: {fn_name}"
                    else:
                        result = await tool_fn(**fn_args)
                except json.JSONDecodeError:
                    result = f"[错误] 工具参数解析失败: {fn_args_raw}"
                except TypeError as e:
                    result = f"[错误] 工具参数不匹配: {e}"
                except Exception as e:
                    result = f"[错误] 工具执行异常: {e}"

                result_summary = str(result)[:300]
                yield _sse_event(
                    "tool_call", agent_name,
                    tool=fn_name,
                    args=fn_args_raw[:200],
                    result=result_summary,
                    status="done",
                )

                local_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result),
                })
        else:
            final_answer = msg.content or ""
            yield _sse_event("status", agent_name, message=f"完成（共 {round_num} 轮）")
            yield _sse_event("answer", agent_name, content=final_answer)
            return

    # 超出最大轮次
    yield _sse_event("status", agent_name, message=f"达到最大轮次 ({max_rounds})，请求模型总结...")
    summary_response = await _create_with_backoff(
        model=model,
        messages=[{"role": "system", "content": system_prompt}] + local_messages + [
            {"role": "user", "content": "请根据已收集到的信息，整理并输出你的分析结果。不要再调用任何工具，直接给出总结。"},
        ],
        tools=None,
        tool_choice=None,
    )
    summary = summary_response.choices[0].message.content or "[达到最大调用轮次且无法生成总结]"
    yield _sse_event("answer", agent_name, content=summary)

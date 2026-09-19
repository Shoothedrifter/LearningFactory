"""
server.py
FastAPI Web 服务：通过 SSE 流式推送 Agent 中间过程和最终答案。

启动方式：
    python server.py
    或
    uvicorn server:app --host 0.0.0.0 --port 8000
"""

import asyncio
import json
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# 必须在导入 agent 模块之前加载 .env
load_dotenv()

from agent import run_main_agent_stream, load_prompt, load_skills

app = FastAPI(title="多智能体系统")

# 挂载静态文件目录
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 内存中的会话存储 {session_id: [messages]}
sessions: dict[str, list[dict]] = {}

# 预加载提示词
MAIN_PROMPT = load_prompt("main_agent.md")
SUB_PROMPTS = {
    "docs_researcher": load_prompt("docs_researcher.md"),
    "repo_analyzer": load_prompt("repo_analyzer.md"),
    "web_researcher": load_prompt("web_researcher.md"),
    "file_writer": load_prompt("file_writer.md"),  # P3：专职写入引擎
}

# 加载 Skill 并追加到主 Agent 系统提示词
_skills_prompt = load_skills()
if _skills_prompt:
    MAIN_PROMPT += "\n\n" + _skills_prompt


@app.get("/", response_class=HTMLResponse)
async def index():
    """返回聊天前端页面。"""
    html_path = STATIC_DIR / "index.html"
    return html_path.read_text(encoding="utf-8")


@app.post("/chat")
async def chat(request: Request):
    """
    SSE 流式聊天端点。

    请求体:
        {"message": "...", "session_id": "...", "history": [...]}
    返回:
        text/event-stream — 逐行推送 SSE 事件
    """
    body = await request.json()
    user_message = body.get("message", "").strip()
    session_id = body.get("session_id") or str(uuid.uuid4())
    history = body.get("history", [])

    if not user_message:
        return StreamingResponse(
            _wrap_sse([json.dumps({"type": "error", "message": "消息不能为空"}, ensure_ascii=False)]),
            media_type="text/event-stream",
        )

    # 恢复或创建会话
    if session_id not in sessions:
        sessions[session_id] = list(history)
    conversation_history = sessions[session_id]

    # 加入用户消息
    conversation_history.append({"role": "user", "content": user_message})

    async def generate():
        try:
            answer_content = None
            async for event_str in run_main_agent_stream(
                system_prompt=MAIN_PROMPT,
                messages=conversation_history,
                sub_prompts=SUB_PROMPTS,
            ):
                yield event_str

                # 捕获最终答案以便更新会话
                try:
                    event = json.loads(event_str)
                    if event.get("type") == "answer":
                        answer_content = event.get("content", "")
                except (json.JSONDecodeError, AttributeError):
                    pass

            # 更新会话历史
            if answer_content is not None:
                conversation_history.append({"role": "assistant", "content": answer_content})
            else:
                # 如果没有收到答案，回滚用户消息
                conversation_history.pop()

        except Exception as e:
            error_event = json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False)
            yield error_event
            conversation_history.pop()

    return StreamingResponse(
        _wrap_sse(generate()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _wrap_sse(event_gen):
    """把事件生成器包装为 SSE 格式（data: ...\n\n）。"""
    async for event_str in event_gen:
        yield f"data: {event_str}\n\n"


@app.post("/session")
async def create_session():
    """创建新会话，返回 session_id。"""
    sid = str(uuid.uuid4())
    sessions[sid] = []
    return {"session_id": sid}


@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """删除会话。"""
    sessions.pop(session_id, None)
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)

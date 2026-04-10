"""FastAPI backend for solo-agent Web UI.

Provides:
- POST /api/ask: one-shot LLM query
- POST /api/run: agent task execution with streaming results
- WebSocket /ws/chat: multi-turn chat with history
- GET /api/stats: memory stats
- GET /: static HTML UI
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.core.session import AgentSession
from agent.core.observer import Verdict
from agent.llm.base import Message
from agent.llm.ollama_client import OllamaClient
from agent.memory.manager import MemoryManager
from agent.tools.code_executor import CodeExecutor
from agent.tools.file_ops import FileOps
from agent.tools.memory_search import MemorySearchTool
from agent.tools.shell_runner import ShellRunner

app = FastAPI(title="solo-agent", version="0.1.0")

# --- Models ---

class AskRequest(BaseModel):
    prompt: str
    model: str = "gemma3-sp"

class AskResponse(BaseModel):
    response: str

class RunRequest(BaseModel):
    task: str
    model: str = "gemma3-sp"
    max_iter: int = 3

class RunResponse(BaseModel):
    verdict: str
    iterations: int
    summary: str
    trace: list[dict]

class StatsResponse(BaseModel):
    stats: dict


# --- Endpoints ---

@app.post("/api/ask", response_model=AskResponse)
async def api_ask(req: AskRequest):
    llm = OllamaClient(model=req.model)
    response = await llm.generate([Message(role="user", content=req.prompt)])
    return AskResponse(response=response)


@app.post("/api/run", response_model=RunResponse)
async def api_run(req: RunRequest):
    llm = OllamaClient(model=req.model)
    memory = MemoryManager(llm_for_summary=llm)
    tools = [ShellRunner(), FileOps(), CodeExecutor(), MemorySearchTool(memory)]
    session = AgentSession(llm, tools, max_iterations=req.max_iter, memory=memory)
    result = await session.run(req.task)
    trace = [
        {
            "tool": rec.step.tool,
            "args": rec.step.args,
            "ok": rec.result.ok,
            "output": rec.result.output[:500],
            "error": rec.result.error[:300],
        }
        for rec in result.last_trace.records
    ]
    return RunResponse(
        verdict=result.verdict.value,
        iterations=result.iterations,
        summary=result.last_observation.summary,
        trace=trace,
    )


@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    await websocket.accept()
    model = "gemma3-sp"
    system = (
        "あなたは親切で正直なローカルLLMアシスタントです。日本語で簡潔に応答してください。"
        "コードレビューで問題がなければ「問題ありません」と正直に答えてください。"
        "知らないことは知らないと素直に答えてください。"
    )
    history: list[Message] = [Message(role="system", content=system)]
    llm = OllamaClient(model=model)

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            user_text = msg.get("content", "")
            if msg.get("model"):
                model = msg["model"]
                llm = OllamaClient(model=model)

            history.append(Message(role="user", content=user_text))

            # Stream response
            buf = ""
            async for token in llm.stream(history):
                buf += token
                await websocket.send_text(json.dumps({"type": "token", "content": token}))

            history.append(Message(role="assistant", content=buf))
            await websocket.send_text(json.dumps({"type": "done", "content": buf}))
    except WebSocketDisconnect:
        pass


@app.get("/api/stats", response_model=StatsResponse)
async def api_stats():
    mm = MemoryManager()
    return StatsResponse(stats=mm.stats())


# --- Static HTML ---

_HTML = Path(__file__).parent / "static" / "index.html"

@app.get("/")
async def root():
    if _HTML.exists():
        return HTMLResponse(_HTML.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>solo-agent</h1><p>static/index.html not found</p>")

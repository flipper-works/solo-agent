"""Baseline 評価ハーネス。

各タスクを ask / plan / run のいずれかで実行し、JSONLとして保存する。
後で Claude Code (人間/LLMレビュアー) が横断分析する。
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from agent.core.session import AgentSession
from agent.core.planner import Planner
from agent.llm.base import BaseLLM, Message
from agent.llm.ollama_client import OllamaClient
from agent.tools.base import BaseTool
from agent.tools.code_executor import CodeExecutor
from agent.tools.file_ops import FileOps
from agent.tools.shell_runner import ShellRunner


@dataclass
class TaskSpec:
    id: str
    category: str
    modes: list[str]
    prompt: str
    expected: str = ""


@dataclass
class TaskResult:
    id: str
    category: str
    mode: str
    prompt: str
    expected: str
    output: Any = None
    elapsed_sec: float = 0.0
    error: str = ""


def load_tasks(path: Path) -> list[TaskSpec]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [TaskSpec(**t) for t in data["tasks"]]


async def _run_ask(llm: BaseLLM, prompt: str) -> str:
    return await llm.generate([Message(role="user", content=prompt)])


async def _run_plan(llm: BaseLLM, tools: list[BaseTool], prompt: str) -> dict:
    planner = Planner(llm, tools)
    plan = await planner.plan(prompt)
    return plan.model_dump()


async def _run_full(
    llm: BaseLLM, tools: list[BaseTool], prompt: str, max_iter: int
) -> dict:
    session = AgentSession(llm, tools, max_iterations=max_iter, memory=None)
    result = await session.run(prompt)
    return {
        "verdict": result.verdict.value,
        "iterations": result.iterations,
        "summary": result.last_observation.summary,
        "trace": [
            {
                "tool": rec.step.tool,
                "args": rec.step.args,
                "ok": rec.result.ok,
                "output": rec.result.output[:1000],
                "error": rec.result.error[:500],
            }
            for rec in result.last_trace.records
        ],
    }


async def run_eval(
    tasks_path: Path,
    out_dir: Path,
    model: str,
    max_iter: int = 3,
) -> Path:
    tasks = load_tasks(tasks_path)
    llm = OllamaClient(model=model)
    tools: list[BaseTool] = [ShellRunner(), FileOps(), CodeExecutor()]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = out_dir / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "results.jsonl"

    print(f"[eval] {len(tasks)} tasks → {out_file}")
    with out_file.open("w", encoding="utf-8") as f:
        for t in tasks:
            for mode in t.modes:
                t0 = time.time()
                err = ""
                output: Any = None
                try:
                    if mode == "ask":
                        output = await _run_ask(llm, t.prompt)
                    elif mode == "plan":
                        output = await _run_plan(llm, tools, t.prompt)
                    elif mode == "run":
                        output = await _run_full(llm, tools, t.prompt, max_iter)
                    else:
                        err = f"unknown mode: {mode}"
                except Exception as e:
                    err = f"{type(e).__name__}: {e}"
                elapsed = time.time() - t0
                rec = TaskResult(
                    id=t.id,
                    category=t.category,
                    mode=mode,
                    prompt=t.prompt,
                    expected=t.expected,
                    output=output,
                    elapsed_sec=round(elapsed, 2),
                    error=err,
                )
                f.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")
                f.flush()
                status = "ERR" if err else "ok"
                print(f"  [{status}] {t.id} ({mode}) {elapsed:.1f}s")
    return out_file

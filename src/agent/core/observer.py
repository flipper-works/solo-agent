"""Observer: 実行結果を評価し、完了/再計画/失敗を判断。"""
from __future__ import annotations

import json
from enum import Enum

from pydantic import BaseModel

from agent.core.executor import ExecutionTrace
from agent.llm.base import BaseLLM, Message


class Verdict(str, Enum):
    DONE = "done"
    REPLAN = "replan"
    FAIL = "fail"


class Observation(BaseModel):
    verdict: Verdict
    summary: str = ""
    next_hint: str = ""


class Observer:
    def __init__(self, llm: BaseLLM) -> None:
        self.llm = llm

    def _trace_to_text(self, trace: ExecutionTrace) -> str:
        lines = []
        for i, rec in enumerate(trace.records, 1):
            lines.append(
                f"[step {i}] tool={rec.step.tool} args={rec.step.args} "
                f"ok={rec.result.ok}\n  out={rec.result.output[:500]}\n  err={rec.result.error[:300]}"
            )
        return "\n".join(lines)

    async def observe(self, task: str, trace: ExecutionTrace) -> Observation:
        sys = (
            "あなたはローカルLLMエージェントのObserverです。\n"
            "与えられたタスクと実行ログを見て、次のいずれかを判定してください:\n"
            "  done   : タスクは達成された\n"
            "  replan : 修正可能。再計画すべき\n"
            "  fail   : 復帰不能\n"
            "出力は次のJSONのみ:\n"
            '{"verdict": "done|replan|fail", "summary": "<日本語1文>", "next_hint": "<replan時の方針>"}'
        )
        user = f"# タスク\n{task}\n\n# 実行ログ\n{self._trace_to_text(trace)}"
        raw = await self.llm.generate(
            [Message(role="system", content=sys), Message(role="user", content=user)],
            options={"temperature": 0.1},
        )
        # extract JSON
        start = raw.find("{")
        end = raw.rfind("}")
        body = raw[start : end + 1] if start != -1 and end != -1 else raw
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return Observation(verdict=Verdict.FAIL, summary=f"observer parse error: {raw[:200]}")
        return Observation.model_validate(data)

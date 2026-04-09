"""Observer: Verifierの結果を踏まえて completion / replan / fail を判断。

現状は Verifier の passed/issues を見て決定論的に verdict を決める。
LLM呼び出しは Verifier 側に集約済みで、Observer 自身は呼ばない (高速)。
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from agent.core.executor import ExecutionTrace
from agent.core.verifier import BaseVerifier, VerifyResult


class Verdict(str, Enum):
    DONE = "done"
    REPLAN = "replan"
    FAIL = "fail"


class Observation(BaseModel):
    verdict: Verdict
    summary: str = ""
    next_hint: str = ""


class Observer:
    def __init__(self, verifier: BaseVerifier) -> None:
        self.verifier = verifier

    async def observe(self, task: str, trace: ExecutionTrace) -> Observation:
        verify = await self.verifier.verify(task, trace)
        return self._decide(verify, trace)

    def _decide(self, verify: VerifyResult, trace: ExecutionTrace) -> Observation:
        # If a step explicitly failed and Verifier confirms not passed,
        # treat as replanable (let Session decide max_iter cutoff -> fail).
        any_step_failed = any(not r.result.ok for r in trace.records)
        if verify.passed:
            return Observation(
                verdict=Verdict.DONE,
                summary=verify.summary or "タスクは達成されました。",
                next_hint="",
            )
        # not passed
        next_hint = "; ".join(verify.issues) if verify.issues else verify.summary
        if any_step_failed:
            return Observation(
                verdict=Verdict.REPLAN,
                summary=verify.summary or "ステップが失敗しました。",
                next_hint=next_hint,
            )
        # all steps ok but verify failed -> instructions/quality issue
        return Observation(
            verdict=Verdict.REPLAN,
            summary=verify.summary or "結果が要件を満たしていません。",
            next_hint=next_hint,
        )

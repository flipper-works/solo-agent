"""Verifier and Observer-with-Verifier unit tests."""
from collections.abc import AsyncIterator

import pytest

from agent.core.executor import ExecutionTrace, StepRecord
from agent.core.observer import Observer, Verdict
from agent.core.planner import PlanStep
from agent.core.verifier import LLMVerifier, VerifyResult
from agent.llm.base import BaseLLM, Message
from agent.tools.base import ToolResult


class StubLLM(BaseLLM):
    def __init__(self, payload: str) -> None:
        self.payload = payload

    async def generate(self, messages: list[Message], **kwargs) -> str:
        return self.payload

    async def stream(self, messages: list[Message], **kwargs) -> AsyncIterator[str]:
        yield self.payload


class StubVerifier:
    def __init__(self, result: VerifyResult) -> None:
        self.result = result
        self.calls = 0

    async def verify(self, task: str, trace: ExecutionTrace) -> VerifyResult:
        self.calls += 1
        return self.result


def _trace_ok() -> ExecutionTrace:
    return ExecutionTrace(
        records=[
            StepRecord(
                step=PlanStep(tool="shell_runner", args={"command": "echo hi"}),
                result=ToolResult(ok=True, output="hi"),
            )
        ]
    )


def _trace_failed() -> ExecutionTrace:
    return ExecutionTrace(
        records=[
            StepRecord(
                step=PlanStep(tool="shell_runner", args={"command": "false"}),
                result=ToolResult(ok=False, error="exit 1"),
            )
        ]
    )


@pytest.mark.asyncio
async def test_llm_verifier_parses_passed():
    llm = StubLLM('{"passed": true, "issues": [], "summary": "ok"}')
    v = LLMVerifier(llm)
    r = await v.verify("task", _trace_ok())
    assert r.passed is True
    assert r.summary == "ok"


@pytest.mark.asyncio
async def test_llm_verifier_parses_issues():
    llm = StubLLM(
        '{"passed": false, "issues": ["数値が違う", "桁数不足"], "summary": "未達成"}'
    )
    v = LLMVerifier(llm)
    r = await v.verify("task", _trace_ok())
    assert r.passed is False
    assert len(r.issues) == 2


@pytest.mark.asyncio
async def test_llm_verifier_handles_garbage():
    llm = StubLLM("not json at all")
    v = LLMVerifier(llm)
    r = await v.verify("task", _trace_ok())
    assert r.passed is False
    assert "parse error" in r.issues[0]


@pytest.mark.asyncio
async def test_observer_done_when_passed():
    sv = StubVerifier(VerifyResult(passed=True, summary="完了"))
    obs = Observer(sv)
    o = await obs.observe("task", _trace_ok())
    assert o.verdict == Verdict.DONE
    assert sv.calls == 1


@pytest.mark.asyncio
async def test_observer_replan_when_step_failed():
    sv = StubVerifier(
        VerifyResult(passed=False, issues=["コマンド失敗"], summary="未完了")
    )
    obs = Observer(sv)
    o = await obs.observe("task", _trace_failed())
    assert o.verdict == Verdict.REPLAN
    assert "コマンド失敗" in o.next_hint


@pytest.mark.asyncio
async def test_observer_replan_when_steps_ok_but_verify_fails():
    sv = StubVerifier(
        VerifyResult(passed=False, issues=["指示違反"], summary="字面違反")
    )
    obs = Observer(sv)
    o = await obs.observe("task", _trace_ok())
    assert o.verdict == Verdict.REPLAN
    assert "指示違反" in o.next_hint

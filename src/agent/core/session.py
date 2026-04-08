"""Session: Plan→Execute→Observe ループの司令塔。"""
from __future__ import annotations

from dataclasses import dataclass

from agent.core.executor import ExecutionTrace, Executor
from agent.core.observer import Observation, Observer, Verdict
from agent.core.planner import Planner
from agent.infra.logger import get_logger
from agent.llm.base import BaseLLM
from agent.tools.base import BaseTool

log = get_logger(__name__)


@dataclass
class SessionResult:
    verdict: Verdict
    iterations: int
    last_trace: ExecutionTrace
    last_observation: Observation


class AgentSession:
    def __init__(
        self,
        llm: BaseLLM,
        tools: list[BaseTool],
        max_iterations: int = 3,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.max_iterations = max_iterations
        self.planner = Planner(llm, tools)
        self.executor = Executor(tools)
        self.observer = Observer(llm)

    async def run(self, task: str) -> SessionResult:
        history: list[str] = []
        trace: ExecutionTrace = ExecutionTrace()
        obs: Observation | None = None
        log.info("session_start", task=task, max_iterations=self.max_iterations)
        for i in range(1, self.max_iterations + 1):
            prior = "\n\n".join(history) if history else ""
            log.info("plan_start", iteration=i)
            plan = await self.planner.plan(task, prior_context=prior)
            log.info("plan_done", iteration=i, steps=len(plan.steps))
            trace = await self.executor.run(plan)
            for j, rec in enumerate(trace.records, 1):
                log.info(
                    "step_executed",
                    iteration=i,
                    step=j,
                    tool=rec.step.tool,
                    ok=rec.result.ok,
                    error=rec.result.error[:200] if rec.result.error else "",
                )
            obs = await self.observer.observe(task, trace)
            log.info("observation", iteration=i, verdict=obs.verdict.value, summary=obs.summary)
            if obs.verdict == Verdict.DONE:
                log.info("session_end", verdict="done", iterations=i)
                return SessionResult(Verdict.DONE, i, trace, obs)
            if obs.verdict == Verdict.FAIL:
                log.warning("session_end", verdict="fail", iterations=i)
                return SessionResult(Verdict.FAIL, i, trace, obs)
            # build history snippet for next planner round
            lines = [f"## 試行{i}"]
            for j, rec in enumerate(trace.records, 1):
                lines.append(
                    f"step{j}: tool={rec.step.tool} args={rec.step.args} ok={rec.result.ok}"
                )
                if rec.result.output:
                    lines.append(f"  out: {rec.result.output[:300]}")
                if rec.result.error:
                    lines.append(f"  err: {rec.result.error[:300]}")
            lines.append(f"observer: {obs.summary}  next_hint: {obs.next_hint}")
            history.append("\n".join(lines))
        assert obs is not None
        log.warning("session_end", verdict=obs.verdict.value, iterations=self.max_iterations)
        return SessionResult(obs.verdict, self.max_iterations, trace, obs)

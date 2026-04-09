"""Executor: Plan に沿ってツールを順次実行する。"""
from __future__ import annotations

from dataclasses import dataclass, field

from agent.core.planner import Plan, PlanStep
from agent.infra.safety import SafetyViolation, check_step
from agent.tools.base import BaseTool, ToolResult


@dataclass
class StepRecord:
    step: PlanStep
    result: ToolResult


@dataclass
class ExecutionTrace:
    records: list[StepRecord] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return all(r.result.ok for r in self.records)


class Executor:
    def __init__(self, tools: list[BaseTool]) -> None:
        self.registry: dict[str, BaseTool] = {t.name: t for t in tools}

    async def run(self, plan: Plan) -> ExecutionTrace:
        trace = ExecutionTrace()
        for step in plan.steps:
            tool = self.registry.get(step.tool)
            if tool is None:
                trace.records.append(
                    StepRecord(
                        step=step,
                        result=ToolResult(ok=False, error=f"unknown tool: {step.tool}"),
                    )
                )
                break
            try:
                check_step(step.tool, step.args)
            except SafetyViolation as e:
                trace.records.append(
                    StepRecord(
                        step=step,
                        result=ToolResult(ok=False, error=f"SafetyViolation: {e}"),
                    )
                )
                break
            result = await tool.execute(**step.args)
            trace.records.append(StepRecord(step=step, result=result))
            if not result.ok:
                break
        return trace

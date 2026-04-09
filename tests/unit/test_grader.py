"""Grader unit tests with stub LLM."""
import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from agent.eval.grader import Grader, render_markdown
from agent.llm.base import BaseLLM, Message


class StubLLM(BaseLLM):
    def __init__(self, payloads: list[str]) -> None:
        self.payloads = payloads
        self.calls = 0

    async def generate(self, messages: list[Message], **kwargs) -> str:
        p = self.payloads[self.calls % len(self.payloads)]
        self.calls += 1
        return p

    async def stream(self, messages: list[Message], **kwargs) -> AsyncIterator[str]:
        yield self.payloads[0]


@pytest.mark.asyncio
async def test_grader_grade_one_score_2():
    llm = StubLLM(['{"score": 2, "reason": "完璧"}'])
    g = Grader(llm)
    grade = await g.grade_one(
        {
            "id": "x",
            "category": "code",
            "mode": "ask",
            "prompt": "FizzBuzz書いて",
            "expected": "正しいコード",
            "output": "for i in range(...)",
        }
    )
    assert grade.score == 2
    assert "完璧" in grade.reason


@pytest.mark.asyncio
async def test_grader_grade_one_handles_garbage():
    llm = StubLLM(["this is not json"])
    g = Grader(llm)
    grade = await g.grade_one(
        {"id": "x", "category": "k", "mode": "ask", "prompt": "p", "expected": "e", "output": "o"}
    )
    assert grade.score == 0
    assert "parse error" in grade.reason


@pytest.mark.asyncio
async def test_grader_grade_file_aggregates(tmp_path: Path):
    f = tmp_path / "results.jsonl"
    rows = [
        {
            "id": "t1", "category": "code", "mode": "ask",
            "prompt": "p1", "expected": "e1", "output": "o1", "error": "", "elapsed_sec": 1,
        },
        {
            "id": "t2", "category": "code", "mode": "ask",
            "prompt": "p2", "expected": "e2", "output": "o2", "error": "", "elapsed_sec": 1,
        },
        {
            "id": "t3", "category": "knowledge", "mode": "ask",
            "prompt": "p3", "expected": "e3", "output": "o3", "error": "", "elapsed_sec": 1,
        },
    ]
    f.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    llm = StubLLM([
        '{"score": 2, "reason": "ok1"}',
        '{"score": 1, "reason": "partial"}',
        '{"score": 0, "reason": "wrong"}',
    ])
    g = Grader(llm)
    report = await g.grade_file(f)
    assert report.total_tasks == 3
    assert report.total_score == 3  # 2 + 1 + 0
    assert report.max_score == 6
    assert len(report.failures) == 2  # t2 (1) and t3 (0)
    assert report.by_category["code"]["score"] == 3
    assert report.by_category["code"]["count"] == 2
    assert report.by_category["knowledge"]["score"] == 0


def test_render_markdown_contains_total():
    from agent.eval.grader import GradeReport, TaskGrade

    report = GradeReport(
        source_file="x.jsonl",
        total_tasks=2,
        total_score=3,
        max_score=4,
        by_category={"code": {"score": 3, "max": 4, "count": 2}},
        grades=[
            TaskGrade(id="t1", category="code", mode="ask", score=2, reason="ok"),
            TaskGrade(id="t2", category="code", mode="ask", score=1, reason="partial"),
        ],
        failures=[
            TaskGrade(id="t2", category="code", mode="ask", score=1, reason="partial"),
        ],
    )
    md = render_markdown(report)
    assert "3 / 4" in md
    assert "75.0%" in md
    assert "t2" in md
    assert "code" in md

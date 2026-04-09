"""LLM-as-judge による評価結果の自動採点。

入力: 評価ハーネスが吐いた results.jsonl (baseline / replan / multiturn 形式)
出力: 各タスク・各カテゴリのスコア + 不合格タスク一覧
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from agent.llm.base import BaseLLM, Message
from agent.llm.ollama_client import OllamaClient


class Grade(BaseModel):
    score: int = Field(ge=0, le=2, description="0=失敗 / 1=部分合格 / 2=合格")
    reason: str = Field(default="", description="採点理由 (1〜2文)")


@dataclass
class TaskGrade:
    id: str
    category: str
    mode: str
    score: int
    reason: str
    error: str = ""


@dataclass
class GradeReport:
    source_file: str
    total_tasks: int
    total_score: int
    max_score: int
    by_category: dict[str, dict[str, int]] = field(default_factory=dict)
    grades: list[TaskGrade] = field(default_factory=list)
    failures: list[TaskGrade] = field(default_factory=list)


_GRADER_SYSTEM = (
    "あなたはAIエージェント評価結果の厳しい採点者です。"
    "タスク (prompt) と期待 (expected) と実際の出力 (output) を照合し、"
    "0〜2 の整数で採点してください。\n"
    "  2 = 期待をほぼ完全に満たしている\n"
    "  1 = 部分的に満たしている (重要な欠落がある)\n"
    "  0 = 期待を満たしていない、または明らかな誤り\n\n"
    "出力は次のJSONのみ:\n"
    '{"score": 0|1|2, "reason": "<日本語1〜2文>"}'
)


def _result_to_brief(rec: dict) -> str:
    """results.jsonl の1レコードを採点用テキストに整形。"""
    mode = rec.get("mode", "?")
    if rec.get("error"):
        return f"[ERROR] {rec['error']}"
    out: Any = rec.get("output")
    if mode == "ask":
        return str(out)[:2000]
    if mode == "plan":
        return f"PLAN: {json.dumps(out, ensure_ascii=False)[:1500]}"
    if mode == "run":
        if not isinstance(out, dict):
            return str(out)[:1500]
        lines = [
            f"verdict={out.get('verdict')} iterations={out.get('iterations')}",
            f"summary: {out.get('summary', '')}",
            "trace:",
        ]
        for i, t in enumerate(out.get("trace", []), 1):
            mark = "OK" if t.get("ok") else "ERR"
            args = json.dumps(t.get("args", {}), ensure_ascii=False)[:200]
            lines.append(f"  [{i}] {mark} {t.get('tool')} {args}")
            if t.get("output"):
                lines.append(f"      out: {str(t['output'])[:200]}")
            if t.get("error"):
                lines.append(f"      err: {str(t['error'])[:200]}")
        return "\n".join(lines)[:2500]
    return str(out)[:1500]


class Grader:
    def __init__(self, llm: BaseLLM | None = None) -> None:
        self.llm = llm or OllamaClient()

    async def grade_one(self, rec: dict) -> Grade:
        prompt = rec.get("prompt", "")
        expected = rec.get("expected", "")
        actual = _result_to_brief(rec)
        user = (
            f"# タスクの prompt\n{prompt}\n\n"
            f"# 期待 (expected)\n{expected}\n\n"
            f"# 実際の出力 (mode={rec.get('mode')})\n{actual}"
        )
        raw = await self.llm.generate(
            [
                Message(role="system", content=_GRADER_SYSTEM),
                Message(role="user", content=user),
            ],
            options={"temperature": 0.0},
            format="json",
        )
        start = raw.find("{")
        end = raw.rfind("}")
        body = raw[start : end + 1] if start != -1 and end != -1 else raw
        try:
            data = json.loads(body)
            return Grade.model_validate(data)
        except Exception as e:
            return Grade(score=0, reason=f"grader parse error: {type(e).__name__}: {raw[:120]}")

    async def grade_file(self, results_file: Path) -> GradeReport:
        report = GradeReport(
            source_file=str(results_file),
            total_tasks=0,
            total_score=0,
            max_score=0,
        )
        cat_acc: dict[str, dict[str, int]] = defaultdict(
            lambda: {"score": 0, "max": 0, "count": 0}
        )
        with results_file.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if "id" not in rec or "mode" not in rec:
                    # multi-turn scenario? skip for now (different shape)
                    continue
                grade = await self.grade_one(rec)
                tg = TaskGrade(
                    id=rec["id"],
                    category=rec.get("category", "uncategorized"),
                    mode=rec["mode"],
                    score=grade.score,
                    reason=grade.reason,
                    error=rec.get("error", ""),
                )
                report.grades.append(tg)
                if tg.score < 2:
                    report.failures.append(tg)
                report.total_tasks += 1
                report.total_score += grade.score
                report.max_score += 2
                c = cat_acc[tg.category]
                c["score"] += grade.score
                c["max"] += 2
                c["count"] += 1
        report.by_category = {k: dict(v) for k, v in cat_acc.items()}
        return report


def render_markdown(report: GradeReport) -> str:
    lines: list[str] = []
    lines.append(f"# Auto-grade Report\n")
    lines.append(f"- **Source**: `{report.source_file}`")
    lines.append(
        f"- **Score**: **{report.total_score} / {report.max_score}** "
        f"({100 * report.total_score / max(1, report.max_score):.1f}%)"
    )
    lines.append(f"- **Tasks**: {report.total_tasks}")
    lines.append(f"- **Failures (score < 2)**: {len(report.failures)}\n")

    lines.append("## カテゴリ別\n")
    lines.append("| カテゴリ | 件数 | スコア | 達成率 |")
    lines.append("|---|---|---|---|")
    for cat, v in sorted(report.by_category.items()):
        rate = 100 * v["score"] / max(1, v["max"])
        lines.append(f"| {cat} | {v['count']} | {v['score']}/{v['max']} | {rate:.0f}% |")

    if report.failures:
        lines.append("\n## 不合格タスク (score < 2)\n")
        lines.append("| ID | category | mode | score | 理由 |")
        lines.append("|---|---|---|---|---|")
        for f in report.failures:
            reason = f.reason.replace("|", "\\|")[:200]
            lines.append(f"| {f.id} | {f.category} | {f.mode} | {f.score} | {reason} |")

    lines.append("\n## 全タスクスコア\n")
    lines.append("| ID | mode | score | 理由 |")
    lines.append("|---|---|---|---|")
    for g in report.grades:
        reason = g.reason.replace("|", "\\|")[:150]
        lines.append(f"| {g.id} | {g.mode} | {g.score} | {reason} |")
    return "\n".join(lines) + "\n"

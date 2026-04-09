"""Multi-turn 会話評価ハーネス。

YAML から複数ターンのシナリオを読み、`agent chat` と同じ history 蓄積方式で
LLM に投げ、各ターンの応答を JSONL に保存する。
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

from agent.llm.base import BaseLLM, Message
from agent.llm.ollama_client import OllamaClient


@dataclass
class Scenario:
    id: str
    category: str
    description: str
    turns: list[str]
    expected: str = ""


@dataclass
class TurnResult:
    turn_index: int
    user: str
    assistant: str
    elapsed_sec: float


@dataclass
class ScenarioResult:
    id: str
    category: str
    description: str
    expected: str
    turns: list[TurnResult] = field(default_factory=list)
    error: str = ""


def load_scenarios(path: Path) -> list[Scenario]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Scenario(**s) for s in data["scenarios"]]


async def _run_scenario(
    llm: BaseLLM, scenario: Scenario, system: str
) -> ScenarioResult:
    history: list[Message] = [Message(role="system", content=system)]
    result = ScenarioResult(
        id=scenario.id,
        category=scenario.category,
        description=scenario.description,
        expected=scenario.expected,
    )
    for i, user_msg in enumerate(scenario.turns, 1):
        history.append(Message(role="user", content=user_msg))
        t0 = time.time()
        try:
            reply = await llm.generate(history)
        except Exception as e:
            result.error = f"turn {i}: {type(e).__name__}: {e}"
            return result
        elapsed = time.time() - t0
        history.append(Message(role="assistant", content=reply))
        result.turns.append(
            TurnResult(
                turn_index=i,
                user=user_msg,
                assistant=reply,
                elapsed_sec=round(elapsed, 2),
            )
        )
    return result


async def run_multiturn_eval(
    scenarios_path: Path,
    out_dir: Path,
    model: str,
    system: str = "あなたは親切で正確なローカルLLMアシスタントです。日本語で簡潔に応答してください。",
) -> Path:
    scenarios = load_scenarios(scenarios_path)
    llm = OllamaClient(model=model)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = out_dir / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "multiturn.jsonl"

    print(f"[multiturn-eval] {len(scenarios)} scenarios → {out_file}")
    with out_file.open("w", encoding="utf-8") as f:
        for s in scenarios:
            t0 = time.time()
            r = await _run_scenario(llm, s, system)
            total = round(time.time() - t0, 2)
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
            f.flush()
            status = "ERR" if r.error else "ok"
            print(f"  [{status}] {s.id} ({len(s.turns)} turns) {total}s")
    return out_file

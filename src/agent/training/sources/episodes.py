"""ChromaDB エピソード記憶を SFTRecord に変換。

成功エピソード (verdict=done) のみを学習データに採用。
失敗エピソードは負例にもなり得るが、現状は除外 (DPO等で別途扱う)。
"""
from __future__ import annotations

from pathlib import Path

from agent.memory.long_term import LongTermMemory
from agent.training.schema import SFTMessage, SFTRecord


_PLANNER_SYSTEM = (
    "あなたはローカルLLMエージェントのPlannerです。"
    "ユーザーのタスクを最小ステップで達成する計画を立ててください。"
)


def episodes_to_records(
    persist_dir: Path = Path("data/chroma"),
    collection: str = "episodes",
    only_done: bool = True,
) -> list[SFTRecord]:
    store = LongTermMemory(persist_dir=persist_dir, collection=collection)
    if store.count() == 0:
        return []
    # search with empty query returns nothing in chroma; iterate via get
    raw = store._col.get()  # type: ignore[attr-defined]
    docs = raw.get("documents") or []
    metas = raw.get("metadatas") or []

    records: list[SFTRecord] = []
    for doc, meta in zip(docs, metas):
        verdict = (meta or {}).get("verdict", "")
        if only_done and verdict != "done":
            continue
        # parse stored text: "task: ...\nverdict: ...\niterations: ...\nsummary: ..."
        task_line = next((l for l in doc.split("\n") if l.startswith("task:")), "")
        summary_line = next((l for l in doc.split("\n") if l.startswith("summary:")), "")
        task = task_line.removeprefix("task:").strip()
        summary = summary_line.removeprefix("summary:").strip()
        if not task:
            continue
        records.append(
            SFTRecord(
                messages=[
                    SFTMessage(role="system", content=_PLANNER_SYSTEM),
                    SFTMessage(role="user", content=task),
                    SFTMessage(role="assistant", content=summary or "(完了)"),
                ],
                source="episodes",
                tag="planner_recovery",
            )
        )
    return records

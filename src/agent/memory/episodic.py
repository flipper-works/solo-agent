"""エピソード記憶: 過去タスクの成功/失敗パターンを保存・検索。

L3 (ChromaDB) の専用コレクションとして実装。タスク内容 + verdict を本文に
含めて保存することで「似たタスクで前回どうなったか」を検索できる。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from agent.memory.long_term import LongTermMemory, MemoryItem


@dataclass
class Episode:
    task: str
    verdict: str  # done | replan | fail
    summary: str
    iterations: int


class EpisodicMemory:
    def __init__(self, persist_dir: Path = Path("data/chroma")) -> None:
        self._store = LongTermMemory(persist_dir=persist_dir, collection="episodes")

    def store(self, ep: Episode) -> None:
        text = (
            f"task: {ep.task}\nverdict: {ep.verdict}\n"
            f"iterations: {ep.iterations}\nsummary: {ep.summary}"
        )
        self._store.add(
            item_id=str(uuid.uuid4()),
            text=text,
            metadata={
                "verdict": ep.verdict,
                "iterations": ep.iterations,
                "task_preview": ep.task[:200],
            },
        )

    def search(self, query: str, top_k: int = 3) -> list[MemoryItem]:
        return self._store.search(query, top_k=top_k)

    def count(self) -> int:
        return self._store.count()

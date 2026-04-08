"""3層メモリのオーケストレータ (L1 + L3、L2は将来拡張)。"""
from __future__ import annotations

from pathlib import Path

from agent.memory.episodic import Episode, EpisodicMemory
from agent.memory.long_term import LongTermMemory, MemoryItem
from agent.memory.short_term import ShortTermMemory, Turn


class MemoryManager:
    def __init__(
        self,
        persist_dir: Path = Path("data/chroma"),
        short_term_max: int = 32,
    ) -> None:
        self.short = ShortTermMemory(max_turns=short_term_max)
        self.long = LongTermMemory(persist_dir=persist_dir)
        self.episodic = EpisodicMemory(persist_dir=persist_dir)

    # --- short term ---
    def add_turn(self, role: str, content: str) -> None:
        self.short.add(Turn(role=role, content=content))

    # --- retrieval for prompt augmentation ---
    def retrieve_context(self, query: str, top_k: int = 3) -> str:
        """Plannerに注入する関連記憶のテキストブロックを返す。"""
        episodes = self.episodic.search(query, top_k=top_k)
        knowledge = self.long.search(query, top_k=top_k)
        if not episodes and not knowledge:
            return ""
        lines: list[str] = []
        if episodes:
            lines.append("## 過去の類似タスク")
            for i, m in enumerate(episodes, 1):
                lines.append(f"{i}. {m.text}")
        if knowledge:
            lines.append("\n## 関連する長期知識")
            for i, m in enumerate(knowledge, 1):
                lines.append(f"{i}. {m.text}")
        return "\n".join(lines)

    # --- store outcomes ---
    def record_episode(
        self, task: str, verdict: str, summary: str, iterations: int
    ) -> None:
        self.episodic.store(
            Episode(task=task, verdict=verdict, summary=summary, iterations=iterations)
        )

    def stats(self) -> dict:
        return {
            "short_term_turns": len(self.short),
            "long_term_items": self.long.count(),
            "episodes": self.episodic.count(),
        }

"""L1 Hot: 現セッションの直近ターンを生のまま保持。"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass
class Turn:
    role: str  # "user" | "assistant" | "system"
    content: str


class ShortTermMemory:
    def __init__(self, max_turns: int = 32) -> None:
        self._buf: deque[Turn] = deque(maxlen=max_turns)

    def add(self, turn: Turn) -> None:
        self._buf.append(turn)

    def all(self) -> list[Turn]:
        return list(self._buf)

    def clear(self) -> None:
        self._buf.clear()

    def __len__(self) -> int:
        return len(self._buf)

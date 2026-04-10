"""Memory search tool: ChromaDB の長期記憶とエピソード記憶をベクトル検索する。

Planner が必要時に明示的に呼び出せるツール版。
(透過注入は MemoryManager.retrieve_context() で既に実装済み。
 本ツールは Planner が「過去の事例を調べたい」と判断した時に使う。)
"""
from __future__ import annotations

from pathlib import Path

from agent.memory.manager import MemoryManager
from agent.tools.base import BaseTool, ToolResult


class MemorySearchTool(BaseTool):
    name = "memory_search"
    description = (
        "過去のタスク履歴や長期記憶をベクトル検索する。"
        "類似のタスクを過去にどう解決したかを調べたい時に使う。"
    )

    def __init__(self, memory: MemoryManager | None = None) -> None:
        self._memory = memory

    def _ensure_memory(self) -> MemoryManager:
        if self._memory is None:
            self._memory = MemoryManager()
        return self._memory

    async def execute(self, query: str, top_k: int = 5) -> ToolResult:
        try:
            mm = self._ensure_memory()
            context = mm.retrieve_context(query, top_k=top_k)
            stats = mm.stats()
            if not context:
                return ToolResult(
                    ok=True,
                    output="関連する記憶が見つかりませんでした。",
                    meta=stats,
                )
            return ToolResult(ok=True, output=context, meta=stats)
        except Exception as e:
            return ToolResult(ok=False, error=f"{type(e).__name__}: {e}")

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "検索クエリ (自然言語)",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返す結果の最大数 (デフォルト5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        }

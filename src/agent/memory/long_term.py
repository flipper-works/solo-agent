"""L3 Cold: ChromaDB によるベクトル検索ベースの長期記憶。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import chromadb
from chromadb.config import Settings


@dataclass
class MemoryItem:
    id: str
    text: str
    metadata: dict
    score: float = 0.0


class LongTermMemory:
    """ChromaDB ローカル永続コレクション。"""

    def __init__(
        self,
        persist_dir: Path = Path("data/chroma"),
        collection: str = "long_term",
    ) -> None:
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(persist_dir),
            settings=Settings(anonymized_telemetry=False),
        )
        self._col = self._client.get_or_create_collection(name=collection)

    def add(self, item_id: str, text: str, metadata: dict | None = None) -> None:
        self._col.add(ids=[item_id], documents=[text], metadatas=[metadata or {"_": ""}])

    def search(self, query: str, top_k: int = 5) -> list[MemoryItem]:
        res = self._col.query(query_texts=[query], n_results=top_k)
        items: list[MemoryItem] = []
        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for i, doc in enumerate(docs):
            items.append(
                MemoryItem(
                    id=ids[i],
                    text=doc,
                    metadata=metas[i] or {},
                    score=float(dists[i]) if dists else 0.0,
                )
            )
        return items

    def count(self) -> int:
        return self._col.count()

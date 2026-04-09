"""SFTデータセットの統合・dedup・split。"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from agent.training.schema import SFTRecord


@dataclass
class DatasetStats:
    total: int
    by_source: dict[str, int]
    by_tag: dict[str, int]
    duplicates_removed: int


def _record_hash(r: SFTRecord) -> str:
    h = hashlib.sha256()
    for m in r.messages:
        h.update(m.role.encode())
        h.update(b"\x00")
        h.update(m.content.encode())
        h.update(b"\x01")
    return h.hexdigest()


def dedupe(records: list[SFTRecord]) -> tuple[list[SFTRecord], int]:
    seen: set[str] = set()
    out: list[SFTRecord] = []
    for r in records:
        h = _record_hash(r)
        if h in seen:
            continue
        seen.add(h)
        out.append(r)
    return out, len(records) - len(out)


def split_train_val(
    records: list[SFTRecord], val_ratio: float = 0.1, seed: int = 42
) -> tuple[list[SFTRecord], list[SFTRecord]]:
    if not records:
        return [], []
    rng = random.Random(seed)
    shuffled = records[:]
    rng.shuffle(shuffled)
    n_val = max(1, int(len(shuffled) * val_ratio)) if len(shuffled) >= 10 else 0
    return shuffled[n_val:], shuffled[:n_val]


def stats(records: list[SFTRecord], dup_removed: int = 0) -> DatasetStats:
    by_source: dict[str, int] = {}
    by_tag: dict[str, int] = {}
    for r in records:
        by_source[r.source] = by_source.get(r.source, 0) + 1
        by_tag[r.tag] = by_tag.get(r.tag, 0) + 1
    return DatasetStats(
        total=len(records),
        by_source=by_source,
        by_tag=by_tag,
        duplicates_removed=dup_removed,
    )

"""SFTRecord を JSONL として書き出す。"""
from __future__ import annotations

import json
from pathlib import Path

from agent.training.schema import SFTRecord


def write_jsonl(records: list[SFTRecord], out_file: Path) -> int:
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r.to_jsonl_dict(), ensure_ascii=False) + "\n")
    return len(records)

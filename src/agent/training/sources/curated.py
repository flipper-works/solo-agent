"""手動キュレーションされた YAML データを SFTRecord に変換。

YAML スキーマ:
  tag: identity
  system: "..."
  examples:
    - user: "..."
      assistant: "..."
    - user: "..."
      assistant: "..."
"""
from __future__ import annotations

from pathlib import Path

import yaml

from agent.training.schema import SFTMessage, SFTRecord


def load_curated_file(path: Path) -> list[SFTRecord]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    tag = data.get("tag", path.stem)
    system = data.get("system", "").strip()
    examples = data.get("examples") or []
    records: list[SFTRecord] = []
    for ex in examples:
        msgs: list[SFTMessage] = []
        if system:
            msgs.append(SFTMessage(role="system", content=system))
        msgs.append(SFTMessage(role="user", content=ex["user"]))
        msgs.append(SFTMessage(role="assistant", content=ex["assistant"]))
        records.append(SFTRecord(messages=msgs, source="curated", tag=tag))
    return records


def load_curated_dir(directory: Path) -> list[SFTRecord]:
    records: list[SFTRecord] = []
    for f in sorted(directory.glob("*.yaml")):
        records.extend(load_curated_file(f))
    return records

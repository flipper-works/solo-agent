"""SFT (Supervised Fine-Tuning) data schema.

ChatML 風の messages 形式 (HF / unsloth / axolotl / TRL 共通)。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SFTMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class SFTRecord(BaseModel):
    messages: list[SFTMessage]
    source: str = Field(default="", description="データ出自 (curated/episodes/augment/oss)")
    tag: str = Field(default="", description="スキル分類 (identity/honesty/unknown 等)")

    def to_jsonl_dict(self) -> dict:
        # exporters drop bookkeeping fields
        return {"messages": [m.model_dump() for m in self.messages]}

"""Whisper adapter skeleton (Phase 3)."""
from __future__ import annotations

from agent.input.base import BaseInputAdapter


class WhisperAdapter(BaseInputAdapter):
    async def to_text(self, input_data: bytes) -> str:
        raise NotImplementedError("WhisperAdapter is Phase 3")

    def supported_types(self) -> list[str]:
        return ["audio/wav", "audio/mp3"]

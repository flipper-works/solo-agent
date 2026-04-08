"""Pass-through text adapter (Phase 1)."""
from __future__ import annotations

from agent.input.base import BaseInputAdapter


class TextAdapter(BaseInputAdapter):
    async def to_text(self, input_data: str) -> str:
        return input_data

    def supported_types(self) -> list[str]:
        return ["text/plain"]

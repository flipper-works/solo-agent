"""Vision adapter skeleton (Phase 2)."""
from __future__ import annotations

from agent.input.base import BaseInputAdapter


class VisionAdapter(BaseInputAdapter):
    async def to_text(self, input_data: bytes) -> str:
        raise NotImplementedError("VisionAdapter is Phase 2")

    def supported_types(self) -> list[str]:
        return ["image/png", "image/jpeg"]

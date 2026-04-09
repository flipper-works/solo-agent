"""Vision adapter: 画像 → 自然言語記述 (Phase 2)。

Gemma 3 のネイティブマルチモーダル能力を使い、画像をテキスト記述に変換する。
これにより Agent Core はモーダル非依存のままで済む (README §5.1)。

注: 専用OCR (Tesseract等) は将来 BaseTool として追加予定 (README §10 backlog)。
"""
from __future__ import annotations

import base64
from pathlib import Path

from agent.input.base import BaseInputAdapter
from agent.llm.base import BaseLLM, Message

_DEFAULT_PROMPT = (
    "この画像の内容を日本語で詳しく記述してください。"
    "見えるオブジェクト、テキスト (もしあれば原文のまま)、レイアウト、色合いを含めること。"
    "推測や創作は避け、観察できる事実のみを書いてください。"
)


class VisionAdapter(BaseInputAdapter):
    def __init__(self, llm: BaseLLM, prompt: str = _DEFAULT_PROMPT) -> None:
        self.llm = llm
        self.prompt = prompt

    async def to_text(self, input_data: bytes | str | Path) -> str:
        """Accept raw bytes, base64 string, or file path."""
        b64 = self._to_b64(input_data)
        msg = Message(role="user", content=self.prompt, images=[b64])
        return await self.llm.generate([msg], options={"temperature": 0.1})

    def _to_b64(self, data: bytes | str | Path) -> str:
        if isinstance(data, (str, Path)):
            p = Path(data)
            if p.exists():
                return base64.b64encode(p.read_bytes()).decode("ascii")
            # assume already base64
            return str(data)
        return base64.b64encode(data).decode("ascii")

    def supported_types(self) -> list[str]:
        return ["image/png", "image/jpeg", "image/webp", "image/gif"]

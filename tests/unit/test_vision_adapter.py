import base64
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from agent.input.vision_adapter import VisionAdapter
from agent.llm.base import BaseLLM, Message


class CapturingLLM(BaseLLM):
    def __init__(self) -> None:
        self.last_messages: list[Message] = []

    async def generate(self, messages: list[Message], **kwargs) -> str:
        self.last_messages = messages
        return "画像には赤い四角が写っています。"

    async def stream(self, messages: list[Message], **kwargs) -> AsyncIterator[str]:
        yield "ok"


@pytest.mark.asyncio
async def test_vision_adapter_from_path(tmp_path: Path) -> None:
    img = tmp_path / "x.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    llm = CapturingLLM()
    out = await VisionAdapter(llm).to_text(img)
    assert "四角" in out
    assert llm.last_messages[0].images is not None
    assert llm.last_messages[0].images[0] == base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode()


@pytest.mark.asyncio
async def test_vision_adapter_from_bytes() -> None:
    llm = CapturingLLM()
    out = await VisionAdapter(llm).to_text(b"\x89PNGfake")
    assert out
    assert llm.last_messages[0].images[0] == base64.b64encode(b"\x89PNGfake").decode()


def test_supported_types() -> None:
    llm = CapturingLLM()
    types = VisionAdapter(llm).supported_types()
    assert "image/png" in types
    assert "image/jpeg" in types

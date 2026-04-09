"""WhisperAdapter unit tests with a fake faster_whisper model."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.input.whisper_adapter import WhisperAdapter


class FakeModel:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def transcribe(self, audio_path, **kwargs):
        segments = [
            SimpleNamespace(text="こんにちは"),
            SimpleNamespace(text=" 世界"),
        ]
        info = SimpleNamespace(language="ja", duration=1.0)
        return segments, info


@pytest.mark.asyncio
async def test_whisper_adapter_to_text_from_path(monkeypatch, tmp_path: Path) -> None:
    a = WhisperAdapter(model_size="tiny", device="cpu")
    monkeypatch.setattr(a, "_model", FakeModel())
    audio = tmp_path / "x.wav"
    audio.write_bytes(b"fake-wav")
    text = await a.to_text(audio)
    assert text == "こんにちは 世界"


@pytest.mark.asyncio
async def test_whisper_adapter_to_text_from_bytes(monkeypatch) -> None:
    a = WhisperAdapter(model_size="tiny", device="cpu")
    monkeypatch.setattr(a, "_model", FakeModel())
    text = await a.to_text(b"fake-wav-bytes")
    assert "こんにちは" in text


def test_supported_types() -> None:
    a = WhisperAdapter()
    types = a.supported_types()
    assert "audio/wav" in types
    assert "audio/mp3" in types

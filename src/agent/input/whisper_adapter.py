"""Whisper adapter: 音声 → 日本語テキスト (Phase 3)。

faster-whisper を使ってローカル CPU/GPU で音声認識する。
モデルは初回呼び出し時に遅延ロード (大きいので)。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.input.base import BaseInputAdapter


class WhisperAdapter(BaseInputAdapter):
    """faster-whisper 経由のローカル音声→テキスト変換。

    Parameters
    ----------
    model_size : str
        "tiny" | "base" | "small" | "medium" | "large-v3" 等
        large-v3 が最高精度だが ~3GB DL。
    device : str
        "cpu" | "cuda" | "auto"
    compute_type : str
        "int8" | "float16" | "float32"
        cpu なら int8 推奨、cuda なら float16 推奨。
    language : str | None
        強制言語 ("ja" 等)。None なら自動検出。
    """

    def __init__(
        self,
        model_size: str = "small",
        device: str = "auto",
        compute_type: str = "int8",
        language: str | None = "ja",
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self._model: Any = None  # lazy

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        # Lazy import to keep cold-start fast for users not using audio
        from faster_whisper import WhisperModel

        self._model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type=self.compute_type,
        )

    async def to_text(self, input_data: bytes | str | Path) -> str:
        """Accept a path string/Path. Bytes input is written to a temp file."""
        self._ensure_model()
        if isinstance(input_data, (str, Path)):
            audio_path = str(input_data)
            cleanup: Path | None = None
        else:
            import tempfile

            with tempfile.NamedTemporaryFile(
                suffix=".wav", delete=False
            ) as f:
                f.write(input_data)
                audio_path = f.name
            cleanup = Path(audio_path)

        try:
            segments, _info = self._model.transcribe(
                audio_path,
                language=self.language,
                vad_filter=True,
            )
            text = "".join(seg.text for seg in segments).strip()
            return text
        finally:
            if cleanup is not None:
                cleanup.unlink(missing_ok=True)

    def supported_types(self) -> list[str]:
        return ["audio/wav", "audio/mp3", "audio/flac", "audio/m4a", "audio/ogg"]

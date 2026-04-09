"""LLM backend abstract interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str
    images: list[str] | None = None  # base64-encoded image data, optional


class BaseLLM(ABC):
    """Backend-agnostic LLM interface (Ollama / vLLM / etc.)."""

    @abstractmethod
    async def generate(self, messages: list[Message], **kwargs) -> str:
        """Return the full response as a single string."""

    @abstractmethod
    def stream(self, messages: list[Message], **kwargs) -> AsyncIterator[str]:
        """Yield response tokens as they are generated."""

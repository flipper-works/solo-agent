"""Ollama HTTP client with streaming support."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from agent.llm.base import BaseLLM, Message


class OllamaClient(BaseLLM):
    """Minimal Ollama /api/chat client."""

    def __init__(
        self,
        model: str = "gemma3:12b",
        base_url: str = "http://localhost:11434",
        timeout: float = 300.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _payload(self, messages: list[Message], stream: bool, **kwargs) -> dict:
        msg_list = []
        for m in messages:
            entry: dict = {"role": m.role, "content": m.content}
            if m.images:
                entry["images"] = m.images
            msg_list.append(entry)
        return {
            "model": self.model,
            "messages": msg_list,
            "stream": stream,
            "options": kwargs.get("options", {}),
        }

    async def generate(self, messages: list[Message], **kwargs) -> str:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.base_url}/api/chat",
                json=self._payload(messages, stream=False, **kwargs),
            )
            r.raise_for_status()
            return r.json()["message"]["content"]

    async def stream(self, messages: list[Message], **kwargs) -> AsyncIterator[str]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json=self._payload(messages, stream=True, **kwargs),
            ) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    if chunk.get("done"):
                        break
                    msg = chunk.get("message", {})
                    if content := msg.get("content"):
                        yield content

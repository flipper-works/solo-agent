"""Ollama HTTP client with streaming support."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from agent.llm.base import BaseLLM, Message


class OllamaClient(BaseLLM):
    """Minimal Ollama /api/chat client.

    Reuses a single httpx.AsyncClient across calls so multi-turn agent
    sessions don't pay TCP/TLS handshake cost on every plan/observe step.
    Increased default timeouts to survive long planner outputs at high
    max_iterations.
    """

    DEFAULT_NUM_PREDICT = 4096
    DEFAULT_NUM_CTX = 8192

    def __init__(
        self,
        model: str = "gemma3:12b",
        base_url: str = "http://localhost:11434",
        timeout: float = 600.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # Persistent client (avoids per-call handshake; reused by stream/generate)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=4, max_connections=8),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _payload(self, messages: list[Message], stream: bool, **kwargs) -> dict:
        msg_list = []
        for m in messages:
            entry: dict = {"role": m.role, "content": m.content}
            if m.images:
                entry["images"] = m.images
            msg_list.append(entry)
        opts = {
            "num_predict": self.DEFAULT_NUM_PREDICT,
            "num_ctx": self.DEFAULT_NUM_CTX,
        }
        opts.update(kwargs.get("options") or {})
        return {
            "model": self.model,
            "messages": msg_list,
            "stream": stream,
            "options": opts,
        }

    async def generate(self, messages: list[Message], **kwargs) -> str:
        r = await self._client.post(
            f"{self.base_url}/api/chat",
            json=self._payload(messages, stream=False, **kwargs),
        )
        r.raise_for_status()
        return r.json()["message"]["content"]

    async def stream(self, messages: list[Message], **kwargs) -> AsyncIterator[str]:
        async with self._client.stream(
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

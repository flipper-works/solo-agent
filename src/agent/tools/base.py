"""Tool layer base classes."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class ToolResult(BaseModel):
    ok: bool
    output: str = ""
    error: str = ""
    meta: dict[str, Any] = {}


class BaseTool(ABC):
    name: str
    description: str

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult: ...

    @abstractmethod
    def get_schema(self) -> dict:
        """Return JSON Schema for LLM tool-calling."""

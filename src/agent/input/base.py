"""InputAdapter abstract base."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseInputAdapter(ABC):
    """全入力モーダルをテキストに統一変換する抽象インターフェース。"""

    @abstractmethod
    async def to_text(self, input_data: Any) -> str: ...

    @abstractmethod
    def supported_types(self) -> list[str]: ...

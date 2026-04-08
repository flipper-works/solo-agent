"""Exponential backoff retry."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
) -> T:
    last: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return await fn()
        except Exception as e:
            last = e
            if attempt < max_attempts - 1:
                await asyncio.sleep(base_delay * (2**attempt))
    assert last is not None
    raise last

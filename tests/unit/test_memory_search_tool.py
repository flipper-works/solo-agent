"""MemorySearchTool unit tests."""
from pathlib import Path

import pytest

from agent.memory.manager import MemoryManager
from agent.tools.memory_search import MemorySearchTool


@pytest.mark.asyncio
async def test_search_empty(tmp_path: Path) -> None:
    mm = MemoryManager(persist_dir=tmp_path / "chroma")
    tool = MemorySearchTool(mm)
    r = await tool.execute(query="hello")
    assert r.ok
    assert "見つかりません" in r.output


@pytest.mark.asyncio
async def test_search_finds_episode(tmp_path: Path) -> None:
    mm = MemoryManager(persist_dir=tmp_path / "chroma2")
    mm.record_episode("fix TypeError in Python", "done", "int cast", 2)
    tool = MemorySearchTool(mm)
    r = await tool.execute(query="TypeError fix", top_k=1)
    assert r.ok
    assert "TypeError" in r.output


def test_schema() -> None:
    tool = MemorySearchTool()
    schema = tool.get_schema()
    assert schema["name"] == "memory_search"
    assert "query" in schema["parameters"]["properties"]

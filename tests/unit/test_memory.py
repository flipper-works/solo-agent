from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from agent.llm.base import BaseLLM, Message
from agent.memory.episodic import Episode, EpisodicMemory
from agent.memory.long_term import LongTermMemory
from agent.memory.manager import MemoryManager
from agent.memory.rolling_summary import RollingSummary
from agent.memory.short_term import ShortTermMemory, Turn


class FakeLLM(BaseLLM):
    def __init__(self) -> None:
        self.calls: list[list[Message]] = []

    async def generate(self, messages: list[Message], **kwargs) -> str:
        self.calls.append(messages)
        return "- 過去の会話を要約しました"

    async def stream(self, messages: list[Message], **kwargs) -> AsyncIterator[str]:
        yield "- 要約"


def test_short_term_ring(tmp_path):
    s = ShortTermMemory(max_turns=3)
    evicted = []
    for i in range(5):
        e = s.add(Turn(role="user", content=str(i)))
        if e:
            evicted.append(e.content)
    assert len(s) == 3
    assert [t.content for t in s.all()] == ["2", "3", "4"]
    assert evicted == ["0", "1"]


@pytest.mark.asyncio
async def test_rolling_summary_fold_in():
    llm = FakeLLM()
    rs = RollingSummary(llm)
    assert not rs
    await rs.fold_in([Turn(role="user", content="hello")])
    assert rs.text.startswith("- 過去")
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_manager_l2_integration(tmp_path):
    llm = FakeLLM()
    mm = MemoryManager(
        persist_dir=tmp_path / "chroma_l2",
        short_term_max=2,
        llm_for_summary=llm,
    )
    await mm.add_turn("user", "first")
    await mm.add_turn("user", "second")
    # eviction starts here -> fold_in invoked
    await mm.add_turn("user", "third")
    assert mm.summary is not None
    assert mm.summary.text != ""
    assert len(llm.calls) >= 1


def test_long_term_persist_and_search(tmp_path):
    lt = LongTermMemory(persist_dir=tmp_path / "chroma", collection="test_lt")
    lt.add("a", "the cat sat on the mat", {"k": "v1"})
    lt.add("b", "dogs run in the park", {"k": "v2"})
    lt.add("c", "feline pet on rug", {"k": "v3"})
    hits = lt.search("cat", top_k=2)
    assert len(hits) == 2
    assert any("cat" in h.text or "feline" in h.text for h in hits)


def test_episodic_store_search(tmp_path):
    em = EpisodicMemory(persist_dir=tmp_path / "chroma2")
    em.store(Episode(task="fix python TypeError", verdict="done", summary="cast int", iterations=2))
    em.store(Episode(task="list directory", verdict="done", summary="ls", iterations=1))
    hits = em.search("TypeError fix", top_k=1)
    assert len(hits) == 1
    assert "TypeError" in hits[0].text


def test_manager_retrieve_context(tmp_path):
    mm = MemoryManager(persist_dir=tmp_path / "chroma3")
    mm.record_episode("write hello.py", "done", "wrote and ran", 1)
    ctx = mm.retrieve_context("create hello world script", top_k=2)
    assert "過去の類似タスク" in ctx
    assert "hello.py" in ctx

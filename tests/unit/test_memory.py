from pathlib import Path

from agent.memory.episodic import Episode, EpisodicMemory
from agent.memory.long_term import LongTermMemory
from agent.memory.manager import MemoryManager
from agent.memory.short_term import ShortTermMemory, Turn


def test_short_term_ring(tmp_path):
    s = ShortTermMemory(max_turns=3)
    for i in range(5):
        s.add(Turn(role="user", content=str(i)))
    assert len(s) == 3
    assert [t.content for t in s.all()] == ["2", "3", "4"]


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

"""SFT pipeline unit tests."""
import json
from pathlib import Path

from agent.training.builder import dedupe, split_train_val, stats
from agent.training.exporter import write_jsonl
from agent.training.schema import SFTMessage, SFTRecord
from agent.training.sources.curated import load_curated_dir, load_curated_file


def _record(uid: int, tag: str = "t") -> SFTRecord:
    return SFTRecord(
        messages=[
            SFTMessage(role="user", content=f"q{uid}"),
            SFTMessage(role="assistant", content=f"a{uid}"),
        ],
        source="curated",
        tag=tag,
    )


def test_dedupe_removes_identical():
    rs = [_record(1), _record(2), _record(1), _record(3)]
    out, removed = dedupe(rs)
    assert len(out) == 3
    assert removed == 1


def test_split_train_val_seeded():
    rs = [_record(i) for i in range(20)]
    t, v = split_train_val(rs, val_ratio=0.2, seed=42)
    assert len(t) + len(v) == 20
    assert len(v) == 4


def test_split_train_val_small():
    rs = [_record(i) for i in range(5)]
    t, v = split_train_val(rs, val_ratio=0.2)
    # too small for val split
    assert len(t) == 5 and len(v) == 0


def test_stats_aggregation():
    rs = [_record(1, "a"), _record(2, "b"), _record(3, "a")]
    s = stats(rs, dup_removed=1)
    assert s.total == 3
    assert s.by_tag == {"a": 2, "b": 1}
    assert s.duplicates_removed == 1


def test_curated_loader(tmp_path: Path):
    yaml_text = (
        "tag: sample\n"
        "system: あなたは親切なアシスタントです。\n"
        "examples:\n"
        '  - user: "こんにちは"\n'
        '    assistant: "こんにちは、お元気ですか？"\n'
        '  - user: "1+1は？"\n'
        '    assistant: "2 です"\n'
    )
    p = tmp_path / "x.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    rs = load_curated_file(p)
    assert len(rs) == 2
    assert rs[0].tag == "sample"
    assert rs[0].source == "curated"
    assert rs[0].messages[0].role == "system"
    assert rs[0].messages[1].role == "user"
    assert rs[0].messages[2].role == "assistant"


def test_curated_dir_loads_real_files():
    rs = load_curated_dir(Path("evals/sft_curated"))
    # 3 yaml files exist (identity / honesty / unknown)
    assert len(rs) >= 6  # at least 2 examples per file
    tags = {r.tag for r in rs}
    assert "identity" in tags
    assert "honesty" in tags
    assert "unknown" in tags


def test_exporter_writes_jsonl(tmp_path: Path):
    rs = [_record(i) for i in range(3)]
    out = tmp_path / "out" / "train.jsonl"
    n = write_jsonl(rs, out)
    assert n == 3
    lines = out.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 3
    first = json.loads(lines[0])
    # bookkeeping fields stripped
    assert "messages" in first
    assert "source" not in first
    assert "tag" not in first

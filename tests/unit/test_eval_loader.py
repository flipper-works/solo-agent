from pathlib import Path

from agent.eval.runner import load_tasks


def test_load_baseline_tasks():
    tasks = load_tasks(Path("evals/tasks/baseline.yaml"))
    assert len(tasks) >= 10
    ids = {t.id for t in tasks}
    assert "k1_python_async" in ids
    assert all(t.modes for t in tasks)
    assert all(m in {"ask", "plan", "run"} for t in tasks for m in t.modes)

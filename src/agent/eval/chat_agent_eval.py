"""ChatAgent (ReAct) 評価ハーネス。

100パターンのテストを投入し、ツール実行の成否を判定する。

判定基準:
1. expect_tool=true のタスクで実際にツールが呼ばれたか
2. verify_command の実行結果に verify_contains が含まれるか
3. verify_output_contains が応答に含まれるか
4. verify_output_not_contains が応答に含まれないか
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import yaml

from agent.core.chat_agent import ChatAgent
from agent.llm.ollama_client import OllamaClient
from agent.tools.code_executor import CodeExecutor
from agent.tools.file_ops import FileOps
from agent.tools.memory_search import MemorySearchTool
from agent.tools.shell_runner import ShellRunner


@dataclass
class TestResult:
    id: str
    prompt: str
    passed: bool
    output: str
    tool_used: bool
    expect_tool: bool
    issues: list[str]
    elapsed_sec: float


def load_tests(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data.get("tasks", [])


async def run_single_test(agent: ChatAgent, test: dict) -> TestResult:
    prompt = test.get("prompt", "")
    expect_tool = test.get("expect_tool", False)
    t0 = time.time()
    issues = []

    if not prompt.strip():
        # Empty prompt test
        try:
            output = await agent.send(prompt)
        except Exception as e:
            output = f"EXCEPTION: {e}"
        elapsed = time.time() - t0
        return TestResult(
            id=test["id"], prompt=prompt, passed=True,
            output=output[:500], tool_used=False,
            expect_tool=False, issues=[], elapsed_sec=round(elapsed, 2),
        )

    try:
        output = await agent.send(prompt)
    except Exception as e:
        output = f"EXCEPTION: {e}"
        issues.append(f"exception: {e}")

    elapsed = time.time() - t0

    # Check if tool was used (by looking for tool markers in output)
    tool_used = any(marker in output for marker in ["🔧", "✅", "❌", "[tool"])

    # Verify tool usage expectation
    if expect_tool and not tool_used:
        issues.append("expected tool usage but none detected")
    if not expect_tool and tool_used:
        issues.append("unexpected tool usage")

    # Verify command (run a shell command and check output)
    verify_cmd = test.get("verify_command")
    verify_contains = test.get("verify_contains")
    if verify_cmd and verify_contains:
        try:
            result = subprocess.run(
                verify_cmd, shell=True, capture_output=True, text=True, timeout=10
            )
            cmd_output = result.stdout + result.stderr
            if verify_contains not in cmd_output:
                issues.append(f"verify_command failed: '{verify_contains}' not in output")
        except Exception as e:
            issues.append(f"verify_command error: {e}")

    # Verify output contains
    verify_out = test.get("verify_output_contains")
    if verify_out and verify_out not in output:
        issues.append(f"output missing: '{verify_out}'")

    # Verify output NOT contains
    verify_not = test.get("verify_output_not_contains")
    if verify_not and verify_not in output:
        issues.append(f"output should not contain: '{verify_not}'")

    passed = len(issues) == 0
    return TestResult(
        id=test["id"], prompt=prompt[:200], passed=passed,
        output=output[:500], tool_used=tool_used,
        expect_tool=expect_tool, issues=issues,
        elapsed_sec=round(elapsed, 2),
    )


async def run_chat_agent_eval(
    tests_path: Path,
    out_dir: Path,
    model: str = "gemma3-sp",
) -> Path:
    tests = load_tests(tests_path)
    llm = OllamaClient(model=model)
    tools = [ShellRunner(), FileOps(), CodeExecutor(), MemorySearchTool()]

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = out_dir / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "chat_agent_results.jsonl"

    print(f"[chat-eval] {len(tests)} tests → {out_file}")

    results = []
    passed = 0
    failed = 0

    with out_file.open("w", encoding="utf-8") as f:
        for i, test in enumerate(tests):
            # Fresh agent for each test (no history leakage)
            agent = ChatAgent(llm, tools)
            result = await run_single_test(agent, test)
            results.append(result)

            if result.passed:
                passed += 1
                status = "✅"
            else:
                failed += 1
                status = "❌"

            print(f"  [{i+1}/{len(tests)}] {status} {result.id} ({result.elapsed_sec}s) {' | '.join(result.issues) if result.issues else ''}")
            f.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")
            f.flush()

    # Summary
    total = len(results)
    rate = 100 * passed / max(1, total)
    print(f"\n[chat-eval] {passed}/{total} passed ({rate:.1f}%)")
    print(f"  failed: {failed}")

    # Write summary
    summary = {
        "total": total, "passed": passed, "failed": failed,
        "pass_rate": round(rate, 1),
        "failures": [
            {"id": r.id, "issues": r.issues, "prompt": r.prompt[:100]}
            for r in results if not r.passed
        ],
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return out_file

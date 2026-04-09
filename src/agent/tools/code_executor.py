"""Python code execution tool (subprocess-isolated).

Two invocation modes:
  - path:  recommended. Run an existing .py file the Planner created via file_ops.
           No long code string in the JSON args -> avoids escape failures.
  - code:  legacy. Inline code string. Still supported for short snippets.
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

from agent.tools.base import BaseTool, ToolResult


class CodeExecutor(BaseTool):
    name = "code_executor"
    description = (
        "Pythonコードを実行し stdout/stderr を返す。"
        "推奨: 先に file_ops で .py ファイルを書き、path 引数で実行する。"
        "短いスニペットなら code 引数も可。"
    )

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    async def execute(
        self, path: str | None = None, code: str | None = None
    ) -> ToolResult:
        if not path and not code:
            return ToolResult(
                ok=False, error="either 'path' or 'code' must be provided"
            )
        if path and code:
            return ToolResult(
                ok=False, error="provide only one of 'path' or 'code'"
            )
        try:
            if path:
                target = Path(path)
                if not target.exists():
                    return ToolResult(ok=False, error=f"file not found: {path}")
                run_path = target
                cleanup: Path | None = None
            else:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".py", delete=False, encoding="utf-8"
                ) as f:
                    assert code is not None
                    f.write(code)
                    run_path = Path(f.name)
                cleanup = run_path

            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                str(run_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout
            )
            if cleanup is not None:
                cleanup.unlink(missing_ok=True)
            return ToolResult(
                ok=proc.returncode == 0,
                output=stdout.decode("utf-8", errors="replace"),
                error=stderr.decode("utf-8", errors="replace"),
                meta={"returncode": proc.returncode},
            )
        except asyncio.TimeoutError:
            return ToolResult(ok=False, error=f"timeout after {self.timeout}s")
        except Exception as e:
            return ToolResult(ok=False, error=f"{type(e).__name__}: {e}")

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "実行する .py ファイルのパス (推奨)",
                    },
                    "code": {
                        "type": "string",
                        "description": "短いPythonスニペット (path との二者択一)",
                    },
                },
            },
        }

"""Python code execution tool (subprocess-isolated)."""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

from agent.tools.base import BaseTool, ToolResult


class CodeExecutor(BaseTool):
    name = "code_executor"
    description = "Pythonコード文字列をサブプロセスで実行し、stdout/stderrを返す。"

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    async def execute(self, code: str) -> ToolResult:
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
                f.write(code)
                tmp_path = Path(f.name)

            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                str(tmp_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout
            )
            tmp_path.unlink(missing_ok=True)
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
                    "code": {"type": "string", "description": "実行するPythonコード"},
                },
                "required": ["code"],
            },
        }

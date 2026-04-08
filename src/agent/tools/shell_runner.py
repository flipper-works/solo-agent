"""Shell command execution tool."""
from __future__ import annotations

import asyncio

from agent.tools.base import BaseTool, ToolResult


class ShellRunner(BaseTool):
    name = "shell_runner"
    description = "シェルコマンドを実行し、stdout/stderr/終了コードを返す。"

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    async def execute(self, command: str, cwd: str | None = None) -> ToolResult:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout
            )
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
                    "command": {"type": "string", "description": "実行するシェルコマンド"},
                    "cwd": {"type": "string", "description": "作業ディレクトリ (省略可)"},
                },
                "required": ["command"],
            },
        }

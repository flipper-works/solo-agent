"""File operations tool: read / write / glob."""
from __future__ import annotations

from glob import glob
from pathlib import Path

from agent.tools.base import BaseTool, ToolResult


class FileOps(BaseTool):
    name = "file_ops"
    description = "ファイルの読み込み / 書き込み / glob検索を行う。"

    async def execute(
        self,
        action: str,
        path: str = "",
        content: str = "",
        pattern: str = "",
    ) -> ToolResult:
        try:
            if action == "read":
                text = Path(path).read_text(encoding="utf-8")
                return ToolResult(ok=True, output=text)
            if action == "write":
                p = Path(path)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")
                return ToolResult(ok=True, output=f"wrote {len(content)} chars to {path}")
            if action == "glob":
                hits = glob(pattern, recursive=True)
                return ToolResult(ok=True, output="\n".join(hits), meta={"count": len(hits)})
            return ToolResult(ok=False, error=f"unknown action: {action}")
        except Exception as e:
            return ToolResult(ok=False, error=f"{type(e).__name__}: {e}")

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["read", "write", "glob"]},
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "pattern": {"type": "string", "description": "globパターン (action=glob時)"},
                },
                "required": ["action"],
            },
        }

"""MCP (Model Context Protocol) server for solo-agent.

Exposes the agent's tools (ShellRunner, FileOps, CodeExecutor,
MemorySearch, Vision, Whisper) via MCP so external clients
(Claude Code, VS Code, etc.) can call them.

Usage:
    uv run python -m agent.mcp_server
    # or via CLI:
    uv run agent mcp-serve
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from agent.tools.base import BaseTool
from agent.tools.code_executor import CodeExecutor
from agent.tools.file_ops import FileOps
from agent.tools.memory_search import MemorySearchTool
from agent.tools.shell_runner import ShellRunner


def _schema_to_mcp_tool(tool: BaseTool) -> Tool:
    """Convert a BaseTool's schema to an MCP Tool definition."""
    schema = tool.get_schema()
    return Tool(
        name=schema["name"],
        description=schema.get("description", ""),
        inputSchema=schema.get("parameters", {"type": "object", "properties": {}}),
    )


def create_server() -> tuple[Server, dict[str, BaseTool]]:
    """Create and configure the MCP server with all agent tools."""
    server = Server("solo-agent")
    tools: dict[str, BaseTool] = {}

    # Register tools
    tool_instances = [
        ShellRunner(),
        FileOps(),
        CodeExecutor(),
        MemorySearchTool(),
    ]
    for t in tool_instances:
        tools[t.name] = t

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [_schema_to_mcp_tool(t) for t in tools.values()]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        tool = tools.get(name)
        if tool is None:
            return [TextContent(type="text", text=f"error: unknown tool '{name}'")]
        try:
            result = await tool.execute(**arguments)
            response = {
                "ok": result.ok,
                "output": result.output,
                "error": result.error,
                "meta": result.meta,
            }
            return [TextContent(type="text", text=json.dumps(response, ensure_ascii=False))]
        except Exception as e:
            return [TextContent(type="text", text=f"error: {type(e).__name__}: {e}")]

    return server, tools


async def main() -> None:
    server, _ = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

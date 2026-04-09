"""MCP server unit tests — verify tool registration and call routing."""
import json

import pytest

from agent.mcp_server import create_server


@pytest.mark.asyncio
async def test_list_tools():
    server, tools = create_server()
    tool_names = set(tools.keys())
    assert "shell_runner" in tool_names
    assert "file_ops" in tool_names
    assert "code_executor" in tool_names
    assert "memory_search" in tool_names


@pytest.mark.asyncio
async def test_call_tool_shell(tmp_path):
    server, tools = create_server()
    # Directly call the tool (bypass MCP transport for unit test)
    result = await tools["shell_runner"].execute(command="echo mcp_test")
    assert result.ok
    assert "mcp_test" in result.output


@pytest.mark.asyncio
async def test_call_tool_file_ops(tmp_path):
    server, tools = create_server()
    p = tmp_path / "mcp.txt"
    result = await tools["file_ops"].execute(action="write", path=str(p), content="mcp!")
    assert result.ok
    result = await tools["file_ops"].execute(action="read", path=str(p))
    assert result.ok
    assert result.output == "mcp!"

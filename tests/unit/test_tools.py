import pytest

from agent.tools.code_executor import CodeExecutor
from agent.tools.file_ops import FileOps
from agent.tools.shell_runner import ShellRunner


@pytest.mark.asyncio
async def test_shell_runner_echo():
    r = await ShellRunner().execute(command="echo hello")
    assert r.ok
    assert "hello" in r.output


@pytest.mark.asyncio
async def test_shell_runner_failure():
    r = await ShellRunner().execute(command="false")
    assert not r.ok
    assert r.meta["returncode"] != 0


@pytest.mark.asyncio
async def test_file_ops_write_read_glob(tmp_path):
    fo = FileOps()
    p = tmp_path / "sub" / "x.txt"
    w = await fo.execute(action="write", path=str(p), content="hi")
    assert w.ok
    r = await fo.execute(action="read", path=str(p))
    assert r.ok and r.output == "hi"
    g = await fo.execute(action="glob", pattern=str(tmp_path / "**" / "*.txt"))
    assert g.ok and str(p) in g.output


@pytest.mark.asyncio
async def test_code_executor_ok():
    r = await CodeExecutor().execute(code="print(1+2)")
    assert r.ok
    assert r.output.strip() == "3"


@pytest.mark.asyncio
async def test_code_executor_error():
    r = await CodeExecutor().execute(code="raise ValueError('boom')")
    assert not r.ok
    assert "ValueError" in r.error

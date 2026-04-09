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


@pytest.mark.asyncio
async def test_code_executor_path_mode(tmp_path):
    p = tmp_path / "x.py"
    p.write_text("print('from path')\n", encoding="utf-8")
    r = await CodeExecutor().execute(path=str(p))
    assert r.ok
    assert r.output.strip() == "from path"


@pytest.mark.asyncio
async def test_code_executor_path_not_found():
    r = await CodeExecutor().execute(path="/nonexistent/xyz.py")
    assert not r.ok
    assert "file not found" in r.error


@pytest.mark.asyncio
async def test_code_executor_requires_one_of():
    r = await CodeExecutor().execute()
    assert not r.ok
    assert "either" in r.error

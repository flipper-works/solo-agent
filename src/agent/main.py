"""Agent CLI entrypoint."""
from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

from pathlib import Path

from agent.core.session import AgentSession
from agent.infra.logger import configure_logging
from agent.llm.base import Message
from agent.llm.ollama_client import OllamaClient
from agent.memory.manager import MemoryManager
from agent.tools.code_executor import CodeExecutor
from agent.tools.file_ops import FileOps
from agent.tools.shell_runner import ShellRunner

app = typer.Typer(help="Local LLM Agent CLI")
console = Console()


@app.command()
def hello() -> None:
    """Sanity check command."""
    console.print("[bold green]agent CLI is alive[/bold green]")


@app.command()
def version() -> None:
    """Show version."""
    from agent import __version__

    console.print(f"agent v{__version__}")


@app.command()
def ask(
    prompt: str = typer.Argument(..., help="One-shot prompt to send to the LLM"),
    model: str = typer.Option("gemma3:12b", "--model", "-m"),
) -> None:
    """Send a single prompt and stream the response."""
    asyncio.run(_ask(prompt, model))


async def _ask(prompt: str, model: str) -> None:
    llm = OllamaClient(model=model)
    messages = [Message(role="user", content=prompt)]
    console.print(f"[dim]>>> {model}[/dim]")
    buf = ""
    async for tok in llm.stream(messages):
        buf += tok
        console.print(tok, end="")
    console.print()


@app.command()
def chat(
    model: str = typer.Option("gemma3:12b", "--model", "-m"),
    system: str = typer.Option(
        "あなたは親切なローカルLLMアシスタントです。日本語で簡潔に応答してください。",
        "--system",
        "-s",
    ),
) -> None:
    """Interactive multi-turn chat (Ctrl-D / 'exit' to quit)."""
    asyncio.run(_chat(model, system))


async def _chat(model: str, system: str) -> None:
    llm = OllamaClient(model=model)
    history: list[Message] = [Message(role="system", content=system)]
    console.print(f"[bold cyan]chat[/bold cyan] model={model}  ([dim]exit で終了[/dim])")
    while True:
        try:
            user = console.input("[bold green]you>[/bold green] ")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]bye[/dim]")
            return
        if user.strip().lower() in {"exit", "quit", ":q"}:
            return
        if not user.strip():
            continue
        history.append(Message(role="user", content=user))
        console.print("[bold magenta]llm>[/bold magenta] ", end="")
        buf = ""
        async for tok in llm.stream(history):
            buf += tok
            console.print(tok, end="")
        console.print()
        history.append(Message(role="assistant", content=buf))


@app.command()
def run(
    task: str = typer.Argument(..., help="エージェントに実行させたいタスク"),
    model: str = typer.Option("gemma3:12b", "--model", "-m"),
    max_iter: int = typer.Option(3, "--max-iter"),
    no_memory: bool = typer.Option(False, "--no-memory", help="メモリ層を無効化"),
) -> None:
    """Plan→Execute→Observe ループでタスクを自律実行。"""
    asyncio.run(_run(task, model, max_iter, no_memory))


async def _run(task: str, model: str, max_iter: int, no_memory: bool) -> None:
    configure_logging(level="INFO", log_file=Path("logs/agent.jsonl"))
    llm = OllamaClient(model=model)
    tools = [ShellRunner(), FileOps(), CodeExecutor()]
    memory = None if no_memory else MemoryManager(llm_for_summary=llm)
    session = AgentSession(llm, tools, max_iterations=max_iter, memory=memory)
    console.print(f"[bold cyan]task:[/bold cyan] {task}")
    result = await session.run(task)
    console.print(f"\n[bold]verdict:[/bold] {result.verdict.value}  iterations={result.iterations}")
    console.print(f"[dim]summary:[/dim] {result.last_observation.summary}")
    console.print("\n[bold]--- trace ---[/bold]")
    for i, rec in enumerate(result.last_trace.records, 1):
        mark = "✅" if rec.result.ok else "❌"
        console.print(f"{mark} [{i}] {rec.step.tool}  args={rec.step.args}")
        if rec.result.output:
            console.print(f"   [dim]out:[/dim] {rec.result.output[:300]}")
        if rec.result.error:
            console.print(f"   [red]err:[/red] {rec.result.error[:300]}")


@app.command()
def stats() -> None:
    """メモリ層の統計を表示。"""
    mm = MemoryManager()
    s = mm.stats()
    console.print("[bold cyan]memory stats[/bold cyan]")
    for k, v in s.items():
        console.print(f"  {k}: {v}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()

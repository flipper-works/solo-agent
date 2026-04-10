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
from agent.input.vision_adapter import VisionAdapter
from agent.input.whisper_adapter import WhisperAdapter
from agent.llm.base import Message
from agent.llm.ollama_client import OllamaClient
from agent.memory.manager import MemoryManager
from agent.tools.code_executor import CodeExecutor
from agent.tools.file_ops import FileOps
from agent.tools.memory_search import MemorySearchTool
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
    model: str = typer.Option("gemma3-sp", "--model", "-m"),
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
    model: str = typer.Option("gemma3-sp", "--model", "-m"),
    system: str = typer.Option(
        "あなたは親切で正直なローカルLLMアシスタントです。日本語で簡潔に応答してください。"
        "コードレビューで問題がなければ「問題ありません」と正直に答えてください。無理に改善点を捏造しないでください。"
        "知らないことは知らないと素直に答えてください。",
        "--system",
        "-s",
    ),
) -> None:
    """Interactive multi-turn chat (Ctrl-D / 'exit' to quit)."""
    asyncio.run(_chat(model, system))


async def _chat(model: str, system: str) -> None:
    from agent.core.chat_agent import ChatAgent

    llm = OllamaClient(model=model)
    tools = [ShellRunner(), FileOps(), CodeExecutor(), MemorySearchTool()]
    agent = ChatAgent(llm, tools, system=system)
    console.print(f"[bold cyan]chat[/bold cyan] model={model}  ([dim]exit で終了 / ツール自動実行対応[/dim])")
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
        console.print("[bold magenta]agent>[/bold magenta] ", end="")
        async for chunk in agent.send_stream(user):
            console.print(chunk, end="")
        console.print()


@app.command()
def run(
    task: str = typer.Argument(..., help="エージェントに実行させたいタスク"),
    model: str = typer.Option("gemma3-sp", "--model", "-m"),
    max_iter: int = typer.Option(3, "--max-iter"),
    no_memory: bool = typer.Option(False, "--no-memory", help="メモリ層を無効化"),
) -> None:
    """Plan→Execute→Observe ループでタスクを自律実行。"""
    asyncio.run(_run(task, model, max_iter, no_memory))


async def _run(task: str, model: str, max_iter: int, no_memory: bool) -> None:
    configure_logging(level="INFO", log_file=Path("logs/agent.jsonl"))
    llm = OllamaClient(model=model)
    memory = None if no_memory else MemoryManager(llm_for_summary=llm)
    tools = [ShellRunner(), FileOps(), CodeExecutor(), MemorySearchTool(memory)]
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
def vision(
    image: Path = typer.Argument(..., help="画像ファイルへのパス"),
    model: str = typer.Option("gemma3-sp", "--model", "-m", help="マルチモーダルモデル"),
    prompt: str = typer.Option(
        "", "--prompt", "-p", help="カスタムプロンプト (省略時はデフォルト記述要求)"
    ),
) -> None:
    """画像を Vision LLM にかけてテキスト記述を取得 (Gemma 3 ネイティブビジョン)。"""
    if not image.exists():
        console.print(f"[red]ファイルが見つかりません:[/red] {image}")
        raise typer.Exit(1)
    asyncio.run(_vision(image, model, prompt))


async def _vision(image: Path, model: str, prompt: str) -> None:
    llm = OllamaClient(model=model)
    adapter = VisionAdapter(llm, prompt=prompt) if prompt else VisionAdapter(llm)
    console.print(f"[dim]>>> {model} reading {image.name}[/dim]")
    text = await adapter.to_text(image)
    console.print(text)


@app.command("sft-build")
def sft_build(
    curated_dir: Path = typer.Option(
        Path("evals/sft_curated"), "--curated", "-c",
        help="手動キュレーションYAMLのディレクトリ"),
    include_episodes: bool = typer.Option(
        True, "--episodes/--no-episodes",
        help="ChromaDBエピソード記憶を含めるか"),
    augment: int = typer.Option(
        0, "--augment", "-a",
        help="各curated例から生成するLLM増強バリエーション数 (0=増強しない)"),
    augment_model: str = typer.Option(
        "gemma3-sp", "--augment-model",
        help="増強に使うLLMモデル"),
    out_dir: Path = typer.Option(
        Path("data/sft"), "--out", "-o", help="出力先ディレクトリ"),
    val_ratio: float = typer.Option(0.1, "--val-ratio"),
) -> None:
    """SFTデータセットを統合・dedup・split して JSONL 出力。"""
    asyncio.run(_sft_build(
        curated_dir, include_episodes, augment, augment_model, out_dir, val_ratio
    ))


async def _sft_build(
    curated_dir: Path,
    include_episodes: bool,
    augment_n: int,
    augment_model: str,
    out_dir: Path,
    val_ratio: float,
) -> None:
    from agent.training.builder import dedupe, split_train_val, stats
    from agent.training.exporter import write_jsonl
    from agent.training.sources.curated import load_curated_dir
    from agent.training.sources.episodes import episodes_to_records

    records: list = []
    if curated_dir.exists():
        c = load_curated_dir(curated_dir)
        console.print(f"[dim]curated:[/dim] {len(c)} records from {curated_dir}")
        records.extend(c)

        if augment_n > 0:
            from agent.training.sources.augment import augment_all
            llm = OllamaClient(model=augment_model)
            console.print(f"[dim]augmenting {len(c)} seeds × {augment_n} variants...[/dim]")
            aug = await augment_all(llm, c, n_variants=augment_n)
            console.print(f"[dim]augmented:[/dim] {len(aug)} new records")
            records.extend(aug)

    if include_episodes:
        try:
            e = episodes_to_records()
            console.print(f"[dim]episodes:[/dim] {len(e)} records from data/chroma")
            records.extend(e)
        except Exception as ex:
            console.print(f"[yellow]episodes skipped:[/yellow] {ex}")

    if not records:
        console.print("[red]no records collected[/red]")
        raise typer.Exit(1)

    deduped, removed = dedupe(records)
    train, val = split_train_val(deduped, val_ratio=val_ratio)
    n_train = write_jsonl(train, out_dir / "train.jsonl")
    n_val = write_jsonl(val, out_dir / "val.jsonl") if val else 0

    s = stats(deduped, dup_removed=removed)
    console.print(f"\n[bold green]done[/bold green]")
    console.print(f"  total deduped: {s.total} (removed {s.duplicates_removed} dups)")
    console.print(f"  by source:     {s.by_source}")
    console.print(f"  by tag:        {s.by_tag}")
    console.print(f"  train: {n_train}  → {out_dir / 'train.jsonl'}")
    if n_val:
        console.print(f"  val:   {n_val}  → {out_dir / 'val.jsonl'}")


@app.command("eval-agent")
def eval_agent(
    tasks: Path = typer.Option(
        Path("evals/tasks/chat_agent.yaml"), "--tasks", "-t"
    ),
    out: Path = typer.Option(Path("evals/results"), "--out", "-o"),
    model: str = typer.Option("gemma3-sp", "--model", "-m"),
) -> None:
    """ChatAgent (ReAct) の100パターン評価を実行。"""
    from agent.eval.chat_agent_eval import run_chat_agent_eval

    out_path = asyncio.run(run_chat_agent_eval(tasks, out, model))
    console.print(f"\n[bold green]done:[/bold green] {out_path}")


@app.command("eval-grade")
def eval_grade(
    results: Path = typer.Argument(..., help="results.jsonl パス"),
    out: Path = typer.Option(None, "--out", "-o",
        help="Markdownレポート出力先 (省略時は標準出力)"),
    model: str = typer.Option("gemma3-sp", "--model", "-m",
        help="採点LLMモデル"),
) -> None:
    """評価結果ファイルを LLM-as-judge で自動採点。"""
    if not results.exists():
        console.print(f"[red]ファイルが見つかりません:[/red] {results}")
        raise typer.Exit(1)
    asyncio.run(_eval_grade(results, out, model))


async def _eval_grade(results: Path, out: Path | None, model: str) -> None:
    from agent.eval.grader import Grader, render_markdown

    grader = Grader(OllamaClient(model=model))
    console.print(f"[dim]>>> grading {results.name} with {model}[/dim]")
    report = await grader.grade_file(results)
    md = render_markdown(report)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        console.print(f"[green]wrote → {out}[/green]")
    else:
        console.print(md)
    console.print(
        f"\n[bold]Total: {report.total_score}/{report.max_score} "
        f"({100 * report.total_score / max(1, report.max_score):.1f}%)[/bold]"
    )


@app.command("eval-chat")
def eval_chat(
    scenarios: Path = typer.Option(
        Path("evals/tasks/multiturn.yaml"), "--scenarios", "-s"
    ),
    out: Path = typer.Option(Path("evals/results"), "--out", "-o"),
    model: str = typer.Option("gemma3-sp", "--model", "-m"),
) -> None:
    """Multi-turn 会話評価を実行 (`agent chat` の品質測定)。"""
    from agent.eval.multiturn import run_multiturn_eval

    out_path = asyncio.run(run_multiturn_eval(scenarios, out, model))
    console.print(f"\n[bold green]done:[/bold green] {out_path}")


@app.command()
def eval(
    tasks: Path = typer.Option(
        Path("evals/tasks/baseline.yaml"), "--tasks", "-t", help="タスク定義YAML"
    ),
    out: Path = typer.Option(Path("evals/results"), "--out", "-o"),
    model: str = typer.Option("gemma3-sp", "--model", "-m"),
    max_iter: int = typer.Option(3, "--max-iter"),
) -> None:
    """ベースライン評価ハーネスを実行 (FT前の弱点抽出用)。"""
    from agent.eval.runner import run_eval

    out_path = asyncio.run(run_eval(tasks, out, model, max_iter))
    console.print(f"\n[bold green]done:[/bold green] {out_path}")


@app.command()
def transcribe(
    audio: Path = typer.Argument(..., help="音声ファイルのパス (.wav/.mp3 等)"),
    model_size: str = typer.Option("small", "--model-size", "-s",
        help="tiny / base / small / medium / large-v3"),
    language: str = typer.Option("ja", "--lang", "-l", help="言語コード (ja/en/auto等、autoは空文字)"),
    device: str = typer.Option("cpu", "--device", "-d",
        help="cpu / cuda (CUDA対応GPUがあれば cuda 推奨、約10〜30倍速)"),
    compute_type: str = typer.Option("", "--compute-type", "-c",
        help="int8 (cpu) / float16 (cuda) / float32。空なら device に応じて自動"),
    output: Path = typer.Option(None, "--output", "-o",
        help="出力ファイル (省略時は標準出力)"),
) -> None:
    """音声ファイルを Whisper で文字起こし。"""
    if not audio.exists():
        console.print(f"[red]ファイルが見つかりません:[/red] {audio}")
        raise typer.Exit(1)
    if not compute_type:
        compute_type = "float16" if device == "cuda" else "int8"
    asyncio.run(_transcribe(audio, model_size, language or None, device, compute_type, output))


async def _transcribe(
    audio: Path,
    model_size: str,
    language: str | None,
    device: str,
    compute_type: str,
    output: Path | None,
) -> None:
    adapter = WhisperAdapter(
        model_size=model_size, language=language, device=device, compute_type=compute_type
    )
    console.print(f"[dim]>>> whisper:{model_size} on {device} reading {audio.name}[/dim]")
    import time
    t0 = time.time()
    text = await adapter.to_text(audio)
    elapsed = time.time() - t0
    console.print(f"[dim]({len(text)} chars in {elapsed:.1f}s)[/dim]")
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        console.print(f"[green]wrote → {output}[/green]")
    else:
        console.print(text)


@app.command()
def web(
    host: str = typer.Option("0.0.0.0", "--host"),
    port: int = typer.Option(8000, "--port", "-p"),
) -> None:
    """Web UI を起動 (ブラウザで操作)。"""
    import uvicorn
    from agent.web.app import app as web_app

    console.print(f"[bold cyan]solo-agent Web UI[/bold cyan] → http://localhost:{port}")
    uvicorn.run(web_app, host=host, port=port, log_level="info")


@app.command("mcp-serve")
def mcp_serve() -> None:
    """MCP サーバーを起動 (stdio transport)。Claude Code / VS Code 等から接続。"""
    from agent.mcp_server import main as mcp_main

    asyncio.run(mcp_main())


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

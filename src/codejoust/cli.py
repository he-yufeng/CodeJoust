from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
from rich.console import Console

from codejoust import __version__
from codejoust.adapters import REGISTRY
from codejoust.core import AgentSpec
from codejoust.report import render_terminal, write_html_report, write_session_json
from codejoust.runner import RunOptions, run_arena


console = Console()


@click.group(invoke_without_command=True)
@click.version_option(__version__, prog_name="codejoust")
@click.pass_context
def main(ctx: click.Context) -> None:
    """CodeJoust — pit AI coding agents against the same task, pick the winner."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@main.command("agents")
def list_agents_cmd() -> None:
    """List known agents you can pass to --agents."""
    seen = set()
    for key, cls in REGISTRY.items():
        if cls in seen:
            continue
        seen.add(cls)
        console.print(f"  [cyan]{cls.name:<14}[/cyan] cli: {cls.default_cli}")


@main.command("run")
@click.argument("task", nargs=-1, required=True)
@click.option(
    "--agents",
    "-a",
    default="claude-code,aider",
    show_default=True,
    help="Comma-separated list of agents. See `codejoust agents`.",
)
@click.option(
    "--repo",
    "-r",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path.cwd(),
    show_default="current directory",
    help="Repo root. Must be a git repo.",
)
@click.option(
    "--timeout",
    type=int,
    default=600,
    show_default=True,
    help="Per-agent timeout in seconds.",
)
@click.option(
    "--test",
    "test_command",
    default=None,
    help="Command to run inside each worktree (e.g. 'pytest -q'). Auto-detected if omitted.",
)
@click.option(
    "--model",
    default=None,
    help="Optional model override passed to every agent (e.g. claude-sonnet-4-6).",
)
@click.option(
    "--keep-worktrees",
    is_flag=True,
    help="Leave worktrees on disk after the run for manual inspection.",
)
@click.option(
    "--html/--no-html",
    "want_html",
    default=True,
    help="Write report.html next to the run artifacts.",
)
@click.option(
    "--open",
    "open_in_browser",
    is_flag=True,
    help="Open the HTML report in your browser when the run ends.",
)
def run_cmd(
    task: tuple[str, ...],
    agents: str,
    repo: Path,
    timeout: int,
    test_command: str | None,
    model: str | None,
    keep_worktrees: bool,
    want_html: bool,
    open_in_browser: bool,
) -> None:
    """Run TASK through every selected agent in isolated git worktrees, then rank them."""
    task_str = " ".join(task).strip()
    if not task_str:
        raise click.UsageError("task description is empty")

    agent_names = [a.strip() for a in agents.split(",") if a.strip()]
    if not agent_names:
        raise click.UsageError("--agents resolved to an empty list")

    specs = [AgentSpec(name=n, cli="", model=model) for n in agent_names]

    console.rule(f"[bold]CodeJoust[/bold] — {len(specs)} agents")
    console.print(f"[dim]task:[/dim] {task_str}")
    console.print(f"[dim]repo:[/dim] {repo}")
    console.print(f"[dim]agents:[/dim] {', '.join(agent_names)}")
    if model:
        console.print(f"[dim]model:[/dim] {model}")

    opts = RunOptions(
        timeout_s=float(timeout),
        test_command=test_command,
        keep_worktrees=keep_worktrees,
    )

    try:
        session = asyncio.run(
            run_arena(
                task=task_str,
                repo_root=repo.resolve(),
                specs=specs,
                opts=opts,
                log_dir=repo.resolve() / ".codejoust" / "logs",
            )
        )
    except Exception as e:
        console.print(f"[red]arena failed:[/red] {e}")
        sys.exit(1)

    render_terminal(session, console=console)

    if session.report_dir:
        write_session_json(session, session.report_dir / "session.json")
        if want_html:
            html_path = session.report_dir / "report.html"
            write_html_report(session, html_path)
            console.print(f"\n[dim]report:[/dim] {html_path}")
            if open_in_browser:
                import webbrowser
                webbrowser.open(html_path.as_uri())

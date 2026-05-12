from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from codejoust import __version__
from codejoust.adapters import REGISTRY
from codejoust.config import load_project_config
from codejoust.core import AgentSpec
from codejoust.doctor import check_agents, known_agent_names
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
    for _key, cls in REGISTRY.items():
        if cls in seen:
            continue
        seen.add(cls)
        console.print(f"  [cyan]{cls.name:<14}[/cyan] cli: {cls.default_cli}")


@main.command("doctor")
@click.option(
    "--agents",
    "agents_text",
    default=None,
    help="Comma-separated agents to check. Defaults to every known adapter.",
)
@click.option("--json", "json_output", is_flag=True, help="Print machine-readable JSON.")
@click.option(
    "--strict",
    is_flag=True,
    help="Exit non-zero if any selected agent CLI is missing.",
)
def doctor_cmd(agents_text: str | None, json_output: bool, strict: bool) -> None:
    """Check whether selected agent CLIs are installed on PATH."""
    names = _parse_agent_names(agents_text) if agents_text else known_agent_names()

    try:
        checks = check_agents(names)
    except ValueError as exc:
        raise click.UsageError(str(exc)) from exc

    if json_output:
        click.echo(json.dumps([c.to_dict() for c in checks], indent=2))
    else:
        table = Table(title="CodeJoust doctor")
        table.add_column("agent", style="cyan")
        table.add_column("cli")
        table.add_column("status")
        table.add_column("path")
        table.add_column("note")
        for check in checks:
            status = "[green]ok[/green]" if check.available else "[red]missing[/red]"
            table.add_row(check.name, check.cli, status, check.path or "", check.note)
        console.print(table)

    if strict and any(not c.available for c in checks):
        sys.exit(1)


@main.command("run")
@click.argument("task", nargs=-1, required=True)
@click.option(
    "--agents",
    "-a",
    default=None,
    help="Comma-separated list of agents. Defaults to codejoust.yaml or claude-code,aider.",
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
    default=None,
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
    "--config",
    "config_path",
    type=click.Path(exists=False, dir_okay=False, path_type=Path),
    default=None,
    help="Project config file. Defaults to codejoust.yaml/.codejoust.yaml if present.",
)
@click.option(
    "--keep-worktrees",
    is_flag=True,
    help="Leave worktrees on disk after the run for manual inspection.",
)
@click.option(
    "--html/--no-html",
    "want_html",
    default=None,
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
    config_path: Path | None,
    keep_worktrees: bool,
    want_html: bool | None,
    open_in_browser: bool,
) -> None:
    """Run TASK through every selected agent in isolated git worktrees, then rank them."""
    task_str = " ".join(task).strip()
    if not task_str:
        raise click.UsageError("task description is empty")

    try:
        cfg = load_project_config(repo, config_path)
    except (OSError, ValueError) as exc:
        raise click.UsageError(str(exc)) from exc

    if agents:
        agent_names = [a.strip() for a in agents.split(",") if a.strip()]
        if not agent_names:
            raise click.UsageError("--agents resolved to an empty list")
        specs = [AgentSpec(name=n, cli="", model=model) for n in agent_names]
    else:
        specs = cfg.agents or [
            AgentSpec(name="claude-code", cli=""),
            AgentSpec(name="aider", cli=""),
        ]
        if model:
            specs = [_with_model(spec, model) for spec in specs]
        elif cfg.model:
            specs = [_with_model(spec, spec.model or cfg.model) for spec in specs]

    timeout_s = timeout if timeout is not None else (cfg.timeout_s or 600)
    test_cmd = test_command if test_command is not None else cfg.test_command
    keep = keep_worktrees or bool(cfg.keep_worktrees)
    html = cfg.html if want_html is None else want_html
    if html is None:
        html = True

    console.rule(f"[bold]CodeJoust[/bold] — {len(specs)} agents")
    console.print(f"[dim]task:[/dim] {task_str}")
    console.print(f"[dim]repo:[/dim] {repo}")
    if cfg.path:
        console.print(f"[dim]config:[/dim] {cfg.path}")
    console.print(f"[dim]agents:[/dim] {', '.join(spec.name for spec in specs)}")
    chosen_model = model or cfg.model
    if chosen_model:
        console.print(f"[dim]model:[/dim] {chosen_model}")

    opts = RunOptions(
        timeout_s=float(timeout_s),
        test_command=test_cmd,
        keep_worktrees=keep,
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
        if html:
            html_path = session.report_dir / "report.html"
            write_html_report(session, html_path)
            console.print(f"\n[dim]report:[/dim] {html_path}")
            if open_in_browser:
                import webbrowser

                webbrowser.open(html_path.as_uri())


def _parse_agent_names(agents_text: str) -> list[str]:
    names = [a.strip() for a in agents_text.split(",") if a.strip()]
    if not names:
        raise click.UsageError("--agents resolved to an empty list")
    return names


def _with_model(spec: AgentSpec, model: str) -> AgentSpec:
    return AgentSpec(
        name=spec.name,
        cli=spec.cli,
        model=model,
        extra_args=list(spec.extra_args),
        env=dict(spec.env),
    )

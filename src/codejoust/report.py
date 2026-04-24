from __future__ import annotations

import html
import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

from codejoust.core import ArenaSession, _run_score

STATUS_STYLE = {
    "success": "green",
    "pending": "dim",
    "running": "yellow",
    "timeout": "red",
    "error": "red",
}


def render_terminal(session: ArenaSession, console: Console | None = None) -> None:
    console = console or Console()

    ranked = sorted(session.runs, key=_run_score, reverse=True)
    winner = session.winner()

    table = Table(title=f"CodeJoust — {session.task[:80]}", title_justify="left")
    table.add_column("#", width=2)
    table.add_column("agent", style="bold")
    table.add_column("status")
    table.add_column("diff", justify="right")
    table.add_column("tests", justify="right")
    table.add_column("cost", justify="right")
    table.add_column("time", justify="right")

    for i, run in enumerate(ranked, 1):
        style = STATUS_STYLE.get(run.status, "")
        diff_str = f"+{run.lines_added}/-{run.lines_removed}" if run.diff else "-"
        if run.tests_total:
            tests_str = f"{run.tests_passed or 0}/{run.tests_total}"
        elif run.status == "success":
            tests_str = "n/a"
        else:
            tests_str = "-"
        cost_str = f"${run.cost_usd:.4f}" if run.cost_usd else "-"
        dur = run.duration_seconds
        time_str = f"{dur:.1f}s" if dur is not None else "-"

        marker = "★" if winner and run.agent == winner.agent else " "
        table.add_row(
            f"{marker}{i}",
            run.agent,
            f"[{style}]{run.status}[/{style}]",
            diff_str,
            tests_str,
            cost_str,
            time_str,
        )

    console.print(table)

    if winner:
        console.print(
            f"\n[bold green]winner:[/bold green] {winner.agent}"
            f"  — git log and merge via: [cyan]cat {session.report_dir}/{winner.agent}.patch | git apply[/cyan]"
        )
    else:
        console.print("\n[red]no successful run.[/red]")

    for run in session.runs:
        if run.status != "success":
            continue
        patch_path = session.report_dir / f"{run.agent}.patch"
        patch_path.write_text(run.diff or "")


def write_html_report(session: ArenaSession, out_path: Path) -> None:
    rows = []
    ranked = sorted(session.runs, key=_run_score, reverse=True)
    winner = session.winner()
    for i, run in enumerate(ranked, 1):
        rows.append(_row_html(i, run, is_winner=(winner and run.agent == winner.agent)))

    diff_blocks = []
    for run in ranked:
        diff_blocks.append(_diff_block_html(run))

    body = f"""
<header>
  <h1>CodeJoust Arena</h1>
  <p class="task">{html.escape(session.task)}</p>
  <p class="meta">
    <span>{html.escape(str(session.repo_root))}</span>
    <span>base: <code>{session.base_commit[:10]}</code> ({html.escape(session.base_branch)})</span>
    <span>{session.started_at.strftime('%Y-%m-%d %H:%M:%S')}</span>
  </p>
</header>

<table class="summary">
  <thead>
    <tr>
      <th>#</th><th>agent</th><th>status</th><th>diff</th>
      <th>tests</th><th>cost</th><th>time</th>
    </tr>
  </thead>
  <tbody>
    {''.join(rows)}
  </tbody>
</table>

<section class="diffs">
  <h2>Patches</h2>
  {''.join(diff_blocks)}
</section>
"""
    out_path.write_text(_HTML_SHELL.format(title="CodeJoust Arena", body=body))


def write_session_json(session: ArenaSession, out_path: Path) -> None:
    data = json.loads(session.model_dump_json())
    out_path.write_text(json.dumps(data, indent=2, default=str))


def _row_html(idx: int, run, is_winner: bool) -> str:
    marker = "★ " if is_winner else ""
    diff_str = f"+{run.lines_added}/−{run.lines_removed}" if run.diff else "—"
    if run.tests_total:
        tests_str = f"{run.tests_passed or 0}/{run.tests_total}"
    elif run.status == "success":
        tests_str = "n/a"
    else:
        tests_str = "—"
    cost_str = f"${run.cost_usd:.4f}" if run.cost_usd else "—"
    dur = run.duration_seconds
    time_str = f"{dur:.1f}s" if dur is not None else "—"
    row_cls = "winner" if is_winner else ""
    return f"""
    <tr class="{row_cls}">
      <td>{marker}{idx}</td>
      <td class="agent">{html.escape(run.agent)}</td>
      <td class="status s-{run.status}">{run.status}</td>
      <td>{diff_str}</td>
      <td>{tests_str}</td>
      <td>{cost_str}</td>
      <td>{time_str}</td>
    </tr>"""


def _diff_block_html(run) -> str:
    if run.status != "success" or not run.diff:
        return f"""
    <article class="diff empty">
      <h3>{html.escape(run.agent)}</h3>
      <p class="note">{html.escape(run.error or f'status: {run.status}')}</p>
    </article>"""
    return f"""
    <article class="diff">
      <h3>{html.escape(run.agent)}</h3>
      <pre><code class="lang-diff">{html.escape(run.diff)}</code></pre>
    </article>"""


_HTML_SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  :root {{
    --bg: #0f1115; --card: #161a22; --fg: #e6e6e6; --muted: #888;
    --ok: #3fb950; --bad: #f85149; --warn: #d29922; --accent: #58a6ff;
    --border: #2a2f3a;
  }}
  html {{ background: var(--bg); color: var(--fg);
         font: 14px/1.5 ui-monospace, SF Mono, Menlo, Consolas, monospace; }}
  body {{ max-width: 1100px; margin: 32px auto; padding: 0 24px; }}
  h1 {{ margin: 0 0 8px; font-size: 24px; }}
  h2 {{ margin: 32px 0 12px; font-size: 18px; color: var(--muted);
        text-transform: uppercase; letter-spacing: 1px; }}
  h3 {{ margin: 0 0 8px; font-size: 15px; }}
  header .task {{ color: var(--accent); margin: 4px 0; font-size: 16px; }}
  header .meta {{ color: var(--muted); font-size: 12px; margin: 0; }}
  header .meta span {{ margin-right: 18px; }}
  table.summary {{ width: 100%; border-collapse: collapse; margin-top: 18px;
                   background: var(--card); border-radius: 6px; overflow: hidden; }}
  table.summary th, table.summary td {{ padding: 10px 14px; text-align: left;
                                        border-bottom: 1px solid var(--border); }}
  table.summary th {{ background: #1c2029; color: var(--muted);
                      font-weight: normal; text-transform: uppercase; font-size: 11px; }}
  table.summary tr.winner td {{ background: rgba(63,185,80,.08); }}
  .agent {{ color: var(--accent); font-weight: 600; }}
  .status.s-success {{ color: var(--ok); }}
  .status.s-error, .status.s-timeout {{ color: var(--bad); }}
  .status.s-running {{ color: var(--warn); }}
  article.diff {{ background: var(--card); border: 1px solid var(--border);
                  border-radius: 6px; padding: 12px 16px; margin-bottom: 16px; }}
  article.diff.empty {{ opacity: 0.55; }}
  article.diff pre {{ margin: 0; overflow: auto; max-height: 480px;
                      background: #0b0d12; padding: 10px 12px; border-radius: 4px; }}
  article.diff pre code {{ white-space: pre; font-size: 12.5px; }}
  .note {{ color: var(--muted); margin: 0; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""

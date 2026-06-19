import io
from pathlib import Path

from rich.console import Console

from codejoust.core import AgentRun, ArenaSession
from codejoust.report import (
    render_markdown,
    render_terminal,
    write_html_report,
    write_session_json,
)


def test_render_markdown_summary(tmp_path: Path) -> None:
    session = ArenaSession(
        task="add a feature",
        repo_root=tmp_path,
        base_commit="abcdef123456",
        base_branch="main",
        report_dir=tmp_path,
    )
    session.add_run(
        AgentRun(
            agent="codex",
            status="success",
            lines_added=10,
            lines_removed=2,
            files_changed=3,
            tests_passed=5,
            tests_total=5,
            cost_usd=0.02,
        )
    )
    session.add_run(AgentRun(agent="claude", status="error", error="boom"))

    md = render_markdown(session)

    assert "## CodeJoust Arena" in md
    assert "| # | Agent | Status | Diff | Tests | Cost |" in md
    assert "codex" in md
    assert "claude" in md
    assert "5/5" in md
    assert "$0.0200" in md
    # codex is the only successful run, so it wins
    assert "**Winner:** codex" in md
    assert "🏆" in md


def test_report_writers_preserve_unicode(tmp_path: Path) -> None:
    session = ArenaSession(
        task="修复中文路径",
        repo_root=tmp_path,
        base_commit="abcdef123456",
        base_branch="main",
        report_dir=tmp_path,
    )
    session.add_run(
        AgentRun(
            agent="codex",
            status="success",
            diff="diff --git a/文件.py b/文件.py\n+print('中文')\n",
            lines_added=1,
        )
    )

    write_html_report(session, tmp_path / "report.html")
    write_session_json(session, tmp_path / "session.json")
    render_terminal(session, Console(file=io.StringIO(), force_terminal=False))

    assert "修复中文路径" in (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "修复中文路径" in (tmp_path / "session.json").read_text(encoding="utf-8")
    assert "文件.py" in (tmp_path / "codex.patch").read_text(encoding="utf-8")

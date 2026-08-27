import json
from datetime import datetime, timedelta
from pathlib import Path

from click.testing import CliRunner

from codejoust.cli import main
from codejoust.core import AgentRun, ArenaSession
from codejoust.evalport import to_resultset, write_evalport_json

START = datetime(2026, 8, 27, 10, 0, 0)


def _session(tmp_path: Path) -> ArenaSession:
    session = ArenaSession(
        task="fix the flaky parser 修复",
        repo_root=tmp_path,
        base_commit="abcdef123456",
        base_branch="main",
        started_at=START,
        report_dir=tmp_path,
    )
    session.add_run(
        AgentRun(
            agent="codex",
            status="success",
            branch="codejoust/run-codex",
            started_at=START,
            finished_at=START + timedelta(seconds=12),
            diff="diff --git a/p.py b/p.py\n+fix\n",
            files_changed=1,
            lines_added=3,
            lines_removed=1,
            input_tokens=800,
            output_tokens=150,
            cost_usd=0.0042,
            tests_passed=3,
            tests_total=4,
            test_command="pytest -q",
        )
    )
    session.add_run(
        AgentRun(
            agent="claude-code",
            status="error",
            error="cli exploded",
            started_at=START,
            finished_at=START + timedelta(seconds=5),
        )
    )
    return session


def test_resultset_maps_session(tmp_path: Path) -> None:
    rs = to_resultset(_session(tmp_path))

    assert rs["version"] == "1.0.0"
    assert rs["suite_id"] == "fix the flaky parser 修复"
    assert rs["run_id"].startswith("codejoust-20260827T100000-")
    assert rs["started_at"] == "2026-08-27T10:00:00"
    assert rs["completed_at"] == "2026-08-27T10:00:12"
    assert rs["runner"]["name"] == "codejoust"
    assert rs["metadata"]["base_commit"] == "abcdef123456"

    codex, claude = rs["results"]
    assert codex["test_case_id"] == "codex"
    assert codex["passed"] is False
    assert codex["actual_output"] == "diff --git a/p.py b/p.py\n+fix\n"
    assert codex["duration_ms"] == 12000
    assert codex["metadata"]["cost_usd"] == 0.0042
    assert codex["metadata"]["input_tokens"] == 800

    gr = codex["grader_results"][0]
    assert gr["grader_id"] == "tests_passed_ratio"
    assert gr["type"] == "custom"
    assert gr["score"] == 0.75
    assert gr["passed"] is False
    assert gr["metadata"]["tests_passed"] == 3
    assert gr["metadata"]["tests_total"] == 4

    assert claude["test_case_id"] == "claude-code"
    assert claude["passed"] is False
    assert claude["grader_results"] == []
    assert claude["error"] == {"type": "runner_error", "message": "cli exploded"}
    assert "actual_output" not in claude

    summary = rs["summary"]
    assert summary["total"] == 2
    assert summary["passed"] == 0
    assert summary["failed"] == 2
    assert summary["pass_rate"] == 0.0
    assert summary["avg_score"] == 0.75
    assert summary["duration_ms"] == 12000
    assert summary["by_grader"]["tests_passed_ratio"] == {
        "passed": 0,
        "failed": 1,
        "avg_score": 0.75,
    }


def test_passing_and_untested_runs_pass(tmp_path: Path) -> None:
    session = ArenaSession(
        task="t", repo_root=tmp_path, base_commit="abc", base_branch="main", started_at=START
    )
    session.add_run(AgentRun(agent="aider", status="success", tests_passed=5, tests_total=5))
    session.add_run(AgentRun(agent="codex", status="success"))

    aider, codex = to_resultset(session)["results"]

    assert aider["passed"] is True
    assert aider["grader_results"][0]["score"] == 1.0
    assert codex["passed"] is True
    assert codex["grader_results"] == []


def test_timeout_run_gets_timeout_error(tmp_path: Path) -> None:
    session = ArenaSession(
        task="t", repo_root=tmp_path, base_commit="abc", base_branch="main", started_at=START
    )
    session.add_run(AgentRun(agent="aider", status="timeout"))

    result = to_resultset(session)["results"][0]

    assert result["passed"] is False
    assert result["error"]["type"] == "timeout"


def test_same_agent_twice_gets_unique_test_case_ids(tmp_path: Path) -> None:
    session = ArenaSession(
        task="t", repo_root=tmp_path, base_commit="abc", base_branch="main", started_at=START
    )
    session.add_run(AgentRun(agent="codex", status="success"))
    session.add_run(AgentRun(agent="codex", status="success"))

    ids = [r["test_case_id"] for r in to_resultset(session)["results"]]

    assert ids == ["codex", "codex-2"]


def test_write_evalport_json(tmp_path: Path) -> None:
    out = tmp_path / "nested" / "resultset.json"
    write_evalport_json(_session(tmp_path), out)

    raw = out.read_text(encoding="utf-8")
    data = json.loads(raw)
    assert "修复" in raw
    assert data["suite_id"] == "fix the flaky parser 修复"
    assert len(data["results"]) == 2


def _stub_arena(monkeypatch, session: ArenaSession) -> None:
    async def fake_arena(**kwargs):
        return session

    monkeypatch.setattr("codejoust.cli.run_arena", fake_arena)


def test_cli_writes_export_only_when_asked(tmp_path: Path, monkeypatch) -> None:
    session = _session(tmp_path)
    _stub_arena(monkeypatch, session)
    runner = CliRunner()

    out = tmp_path / "resultset.json"
    result = runner.invoke(
        main, ["run", "fix", "things", "--repo", str(tmp_path), "--evalport", str(out)]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["results"][0]["test_case_id"] == "codex"

    other = tmp_path / "plain"
    other.mkdir()
    session2 = _session(other)
    _stub_arena(monkeypatch, session2)
    result = runner.invoke(main, ["run", "fix", "things", "--repo", str(other)])
    assert result.exit_code == 0, result.output
    assert not (other / "resultset.json").exists()
    assert {p.name for p in session2.report_dir.iterdir()} == {
        "session.json",
        "report.md",
        "report.html",
        "codex.patch",
    }

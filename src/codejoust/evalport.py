from __future__ import annotations

import json
import uuid
from pathlib import Path

from codejoust import __version__
from codejoust.core import AgentRun, ArenaSession

EVALPORT_VERSION = "1.0.0"
TESTS_GRADER_ID = "tests_passed_ratio"


def to_resultset(session: ArenaSession) -> dict:
    """Map a finished arena session to an EvalPort ResultSet document."""
    results = []
    seen: dict[str, int] = {}
    for run in session.runs:
        # test_case_id must be unique in the document, and the same agent can race twice.
        seen[run.agent] = seen.get(run.agent, 0) + 1
        n = seen[run.agent]
        results.append(_to_result(run, run.agent if n == 1 else f"{run.agent}-{n}"))

    finished = [r.finished_at for r in session.runs if r.finished_at]
    completed_at = max(finished) if finished else None
    scores = [g["score"] for r in results for g in r["grader_results"] if g["score"] is not None]
    passed = sum(1 for r in results if r["passed"])

    summary = {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "skipped": 0,
        "pass_rate": passed / len(results) if results else 0.0,
        "avg_score": sum(scores) / len(scores) if scores else 0.0,
        "by_grader": _by_grader(results),
    }
    if completed_at:
        summary["duration_ms"] = int((completed_at - session.started_at).total_seconds() * 1000)

    data = {
        "version": EVALPORT_VERSION,
        "suite_id": session.task[:64],
        "run_id": f"codejoust-{session.started_at:%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}",
        "started_at": session.started_at.isoformat(),
        "results": results,
        "runner": {"name": "codejoust", "version": __version__},
        "summary": summary,
        "metadata": {
            "task": session.task,
            "repo_root": str(session.repo_root),
            "base_commit": session.base_commit,
            "base_branch": session.base_branch,
        },
    }
    if completed_at:
        data["completed_at"] = completed_at.isoformat()
    return data


def write_evalport_json(session: ArenaSession, out_path: Path) -> None:
    data = to_resultset(session)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _to_result(run: AgentRun, test_case_id: str) -> dict:
    grader_results = []
    if run.tests_total:
        grader_results.append(
            {
                "grader_id": TESTS_GRADER_ID,
                "type": "custom",
                "score": run.test_ratio or 0.0,
                "passed": run.tests_passed == run.tests_total,
                "reason": f"{run.tests_passed or 0}/{run.tests_total} tests passed",
                "metadata": {
                    "tests_passed": run.tests_passed,
                    "tests_total": run.tests_total,
                    "test_command": run.test_command,
                },
            }
        )

    result = {
        "test_case_id": test_case_id,
        "grader_results": grader_results,
        "passed": run.status == "success" and all(g["passed"] for g in grader_results),
        "metadata": {
            "agent": run.agent,
            "status": run.status,
            "cost_usd": run.cost_usd,
            "input_tokens": run.input_tokens,
            "output_tokens": run.output_tokens,
            "files_changed": run.files_changed,
            "lines_added": run.lines_added,
            "lines_removed": run.lines_removed,
            "branch": run.branch,
        },
    }
    if run.diff:
        result["actual_output"] = run.diff
    if run.duration_seconds is not None:
        result["duration_ms"] = int(run.duration_seconds * 1000)
    if run.status == "timeout":
        result["error"] = {"type": "timeout", "message": run.error or "agent timed out"}
    elif run.status == "error":
        result["error"] = {"type": "runner_error", "message": run.error or "agent run failed"}
    return result


def _by_grader(results: list[dict]) -> dict:
    buckets: dict[str, dict] = {}
    for result in results:
        for gr in result["grader_results"]:
            bucket = buckets.setdefault(gr["grader_id"], {"passed": 0, "failed": 0, "scores": []})
            bucket["passed" if gr["passed"] else "failed"] += 1
            if gr["score"] is not None:
                bucket["scores"].append(gr["score"])
    return {
        grader_id: {
            "passed": b["passed"],
            "failed": b["failed"],
            "avg_score": sum(b["scores"]) / len(b["scores"]) if b["scores"] else 0.0,
        }
        for grader_id, b in buckets.items()
    }

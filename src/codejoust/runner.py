from __future__ import annotations

import asyncio
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from codejoust.adapters import AgentAdapter, build_adapter
from codejoust.core import AgentRun, AgentSpec, ArenaSession
from codejoust.worktree import (
    add_worktree,
    current_branch,
    diff_against,
    ensure_git_repo,
    head_commit,
    remove_worktree,
)


_SAFE = re.compile(r"[^a-z0-9]+")


@dataclass
class RunOptions:
    timeout_s: float = 600.0
    test_command: str | None = None
    keep_worktrees: bool = False


def _slug(name: str) -> str:
    return _SAFE.sub("-", name.lower()).strip("-") or "agent"


async def _run_agent(
    adapter: AgentAdapter,
    task: str,
    cwd: Path,
    run: AgentRun,
    opts: RunOptions,
    log_dir: Path,
) -> AgentRun:
    try:
        adapter.check()
    except Exception as e:
        run.status = "error"
        run.error = str(e)
        return run
    return await adapter.run(task, cwd, run, opts.timeout_s, log_dir)


def _detect_test_command(repo: Path) -> str | None:
    # Light heuristic. Users can always override with --test.
    if (repo / "pyproject.toml").exists() or (repo / "pytest.ini").exists():
        if (repo / "tests").exists() or list(repo.glob("test_*.py")):
            return "pytest -q"
    if (repo / "package.json").exists():
        try:
            import json

            pkg = json.loads((repo / "package.json").read_text())
            if "test" in (pkg.get("scripts") or {}):
                return "npm test --silent"
        except Exception:
            return None
    return None


def _run_tests(worktree: Path, command: str) -> tuple[int | None, int | None, str]:
    """Run the test command; return (passed, total, tail)."""
    res = subprocess.run(
        command,
        cwd=str(worktree),
        shell=True,
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = (res.stdout + "\n" + res.stderr).strip()
    tail = "\n".join(output.splitlines()[-40:])
    passed, total = _parse_pytest_summary(output)
    if passed is None:
        passed, total = _parse_jest_summary(output)
    if passed is None:
        # Fallback: treat exit code as a coarse signal so the run still scores.
        total = 1
        passed = 1 if res.returncode == 0 else 0
    return passed, total, tail


def _parse_pytest_summary(output: str) -> tuple[int | None, int | None]:
    # "3 passed, 1 failed, 2 skipped in 0.5s"
    summary_line = None
    for line in output.splitlines():
        s = line.strip()
        if " passed" in s or " failed" in s or " error" in s:
            summary_line = s
    if summary_line is None:
        return None, None
    passed = _count(summary_line, r"(\d+)\s+passed")
    failed = _count(summary_line, r"(\d+)\s+failed")
    errors = _count(summary_line, r"(\d+)\s+error")
    if passed == 0 and failed == 0 and errors == 0:
        return None, None
    return passed, passed + failed + errors


def _parse_jest_summary(output: str) -> tuple[int | None, int | None]:
    # "Tests:       1 failed, 4 passed, 5 total"
    for line in output.splitlines():
        if "Tests:" in line and "total" in line:
            passed = _count(line, r"(\d+)\s+passed")
            failed = _count(line, r"(\d+)\s+failed")
            total = _count(line, r"(\d+)\s+total")
            if total:
                return passed, total
            if passed or failed:
                return passed, passed + failed
    return None, None


def _count(text: str, pattern: str) -> int:
    m = re.search(pattern, text)
    return int(m.group(1)) if m else 0


async def run_arena(
    task: str,
    repo_root: Path,
    specs: list[AgentSpec],
    opts: RunOptions,
    log_dir: Path,
) -> ArenaSession:
    ensure_git_repo(repo_root)
    base = head_commit(repo_root)
    base_branch = current_branch(repo_root)
    session = ArenaSession(
        task=task,
        repo_root=repo_root,
        base_commit=base,
        base_branch=base_branch,
    )

    test_cmd = opts.test_command or _detect_test_command(repo_root)

    worktree_root = repo_root / ".codejoust" / "worktrees"
    session.report_dir = repo_root / ".codejoust" / "runs" / session.started_at.strftime("%Y%m%d-%H%M%S")
    session.report_dir.mkdir(parents=True, exist_ok=True)

    adapters: list[tuple[AgentAdapter, AgentRun, Path, str]] = []
    for spec in specs:
        adapter = build_adapter(spec)
        slug = _slug(spec.name)
        wt = worktree_root / f"{session.started_at.strftime('%H%M%S')}-{slug}"
        branch = f"codejoust/{session.started_at.strftime('%Y%m%d-%H%M%S')}-{slug}"
        remove_worktree(repo_root, wt, branch)  # sanity clean
        add_worktree(repo_root, wt, branch, base)
        run = AgentRun(agent=adapter.name, worktree=wt, branch=branch)
        session.add_run(run)
        adapters.append((adapter, run, wt, branch))

    try:
        await asyncio.gather(
            *[
                _run_agent(adapter, task, wt, run, opts, log_dir / _slug(run.agent))
                for adapter, run, wt, _ in adapters
            ]
        )

        for adapter, run, wt, _ in adapters:
            if run.status != "success":
                continue
            try:
                diff, fc, la, lr = diff_against(repo_root, wt, base)
                run.diff = diff
                run.files_changed = fc
                run.lines_added = la
                run.lines_removed = lr
            except Exception as e:
                run.error = f"diff failed: {e}"
                run.status = "error"
                continue

            if test_cmd:
                run.test_command = test_cmd
                try:
                    passed, total, tail = _run_tests(wt, test_cmd)
                    run.tests_passed = passed
                    run.tests_total = total
                    run.test_output_tail = tail
                except subprocess.TimeoutExpired:
                    run.test_output_tail = "tests timed out"

    finally:
        if not opts.keep_worktrees:
            for _, run, wt, branch in adapters:
                remove_worktree(repo_root, wt, branch)
                run.worktree = None

    return session

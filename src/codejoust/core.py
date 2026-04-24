from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class AgentSpec(BaseModel):
    """An agent that can be asked to solve a task."""

    name: str
    cli: str
    model: Optional[str] = None
    extra_args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class AgentRun(BaseModel):
    """One agent's attempt at one task."""

    agent: str
    status: str = "pending"  # pending | running | success | timeout | error
    worktree: Optional[Path] = None
    branch: Optional[str] = None

    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    diff: str = ""
    files_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0

    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    tests_passed: Optional[int] = None
    tests_total: Optional[int] = None
    test_command: Optional[str] = None
    test_output_tail: str = ""

    error: Optional[str] = None
    stdout_path: Optional[Path] = None
    stderr_path: Optional[Path] = None

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    @property
    def test_ratio(self) -> Optional[float]:
        if self.tests_total and self.tests_total > 0:
            return (self.tests_passed or 0) / self.tests_total
        return None


class ArenaSession(BaseModel):
    """A single arena run — one task, N agents competing."""

    task: str
    repo_root: Path
    base_commit: str
    base_branch: str
    started_at: datetime = Field(default_factory=datetime.now)
    runs: list[AgentRun] = Field(default_factory=list)
    report_dir: Optional[Path] = None

    def add_run(self, run: AgentRun) -> None:
        self.runs.append(run)

    def winner(self) -> Optional[AgentRun]:
        successful = [r for r in self.runs if r.status == "success"]
        if not successful:
            return None
        return max(successful, key=_run_score)


def _run_score(run: AgentRun) -> tuple:
    # Sort key: tests pass ratio first, then cost, then diff size, then duration.
    # None-safe: agents without test info fall to the bottom of the tier.
    ratio = run.test_ratio if run.test_ratio is not None else -1.0
    cost = -run.cost_usd
    diff_penalty = -(run.lines_added + run.lines_removed)
    duration = -(run.duration_seconds or 1e9)
    return (ratio, cost, diff_penalty, duration)

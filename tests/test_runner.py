import asyncio
from pathlib import Path

from codejoust.core import AgentSpec
from codejoust.runner import RunOptions, run_arena


def test_arena_runs_both_agents(tmp_repo: Path, fake_bin: Path, tmp_path: Path) -> None:
    session = asyncio.run(
        run_arena(
            task="add a comment",
            repo_root=tmp_repo,
            specs=[
                AgentSpec(name="claude-code", cli=""),
                AgentSpec(name="aider", cli=""),
            ],
            opts=RunOptions(timeout_s=30, keep_worktrees=False),
            log_dir=tmp_path / "logs",
        )
    )

    assert len(session.runs) == 2
    by_name = {r.agent: r for r in session.runs}

    claude = by_name["claude-code"]
    assert claude.status == "success"
    assert claude.lines_added >= 1, claude.diff
    assert claude.input_tokens == 1200
    assert claude.output_tokens == 300
    assert abs(claude.cost_usd - 0.0042) < 1e-6

    aider = by_name["aider"]
    assert aider.status == "success"
    assert aider.lines_added >= 1
    assert aider.input_tokens == 1100  # "1.1k" -> 1100
    assert aider.output_tokens == 210
    assert abs(aider.cost_usd - 0.0021) < 1e-6


def test_winner_prefers_test_ratio_then_cost(tmp_repo: Path, fake_bin: Path, tmp_path: Path) -> None:
    session = asyncio.run(
        run_arena(
            task="noop",
            repo_root=tmp_repo,
            specs=[
                AgentSpec(name="claude-code", cli=""),
                AgentSpec(name="aider", cli=""),
            ],
            opts=RunOptions(timeout_s=30),
            log_dir=tmp_path / "logs",
        )
    )
    # No tests in the demo repo, so scoring falls back to cost — aider is cheaper.
    winner = session.winner()
    assert winner is not None
    assert winner.agent == "aider"

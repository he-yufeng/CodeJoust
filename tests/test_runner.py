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


def test_codex_adapter_parses_token_count(tmp_repo: Path, fake_bin: Path, tmp_path: Path) -> None:
    session = asyncio.run(
        run_arena(
            task="comment",
            repo_root=tmp_repo,
            specs=[AgentSpec(name="codex", cli="")],
            opts=RunOptions(timeout_s=30),
            log_dir=tmp_path / "logs",
        )
    )
    codex = session.runs[0]
    assert codex.status == "success", codex.error
    assert codex.lines_added >= 1
    assert codex.input_tokens == 800
    assert codex.output_tokens == 150
    assert codex.cost_usd == 0.0  # codex exec output has no $ field


def test_gemini_adapter_parses_result_stats(tmp_repo: Path, fake_bin: Path, tmp_path: Path) -> None:
    session = asyncio.run(
        run_arena(
            task="comment",
            repo_root=tmp_repo,
            specs=[AgentSpec(name="gemini", cli="")],
            opts=RunOptions(timeout_s=30),
            log_dir=tmp_path / "logs",
        )
    )
    gemini = session.runs[0]
    assert gemini.status == "success", gemini.error
    assert gemini.lines_added >= 1
    assert gemini.input_tokens == 640
    assert gemini.output_tokens == 120
    assert gemini.cost_usd == 0.0  # gemini stream-json has no $ field either


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

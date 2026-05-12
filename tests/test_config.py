from pathlib import Path

import pytest
from click.testing import CliRunner

from codejoust.cli import main
from codejoust.config import load_project_config


def test_load_project_config_reads_agents_and_defaults(tmp_path: Path) -> None:
    (tmp_path / "codejoust.yaml").write_text(
        """
agents:
  - claude-code
  - name: codex
    model: gpt-5
    extra_args: ["--reasoning-effort", "high"]
    env:
      CODEX_HOME: .codex-test
test: pytest -q
timeout: 120
model: claude-sonnet-4-6
keep_worktrees: true
html: false
""".lstrip(),
        encoding="utf-8",
    )

    cfg = load_project_config(tmp_path)

    assert cfg.path == tmp_path / "codejoust.yaml"
    assert cfg.test_command == "pytest -q"
    assert cfg.timeout_s == 120
    assert cfg.model == "claude-sonnet-4-6"
    assert cfg.keep_worktrees is True
    assert cfg.html is False
    assert cfg.agents is not None
    assert [agent.name for agent in cfg.agents] == ["claude-code", "codex"]
    assert cfg.agents[1].model == "gpt-5"
    assert cfg.agents[1].extra_args == ["--reasoning-effort", "high"]
    assert cfg.agents[1].env == {"CODEX_HOME": ".codex-test"}


def test_load_project_config_rejects_bad_shape(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("- not\n- a mapping\n", encoding="utf-8")

    with pytest.raises(ValueError, match="top-level"):
        load_project_config(tmp_path, path)


def test_run_uses_project_config(tmp_repo: Path, fake_bin: Path, tmp_path: Path) -> None:
    (tmp_repo / "codejoust.yaml").write_text(
        """
agents: codex
test: python -c "print('1 passed')"
timeout: 30
html: false
""".lstrip(),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        main,
        ["run", "configured task", "--repo", str(tmp_repo)],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    assert "config:" in result.output
    assert "agents:" in result.output
    assert "codex" in result.output
    assert "claude-code" not in result.output

import json

from click.testing import CliRunner

from codejoust.cli import main
from codejoust.doctor import check_agents, known_agent_names


def test_known_agent_names_are_canonical() -> None:
    assert known_agent_names() == ["claude-code", "aider", "codex", "gemini"]


def test_doctor_finds_fake_agent_clis(fake_bin) -> None:
    checks = check_agents(["claude-code", "codex"])

    assert [c.name for c in checks] == ["claude-code", "codex"]
    assert all(c.available for c in checks)
    assert checks[0].path
    assert checks[1].path


def test_doctor_json_output(fake_bin) -> None:
    result = CliRunner().invoke(main, ["doctor", "--agents", "claude-code,codex", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert [item["name"] for item in payload] == ["claude-code", "codex"]
    assert [item["status"] for item in payload] == ["ok", "ok"]


def test_doctor_strict_fails_when_cli_is_missing(monkeypatch, tmp_path) -> None:
    empty_path = tmp_path / "empty-bin"
    empty_path.mkdir()
    monkeypatch.setenv("PATH", str(empty_path))

    result = CliRunner().invoke(main, ["doctor", "--agents", "claude-code", "--json", "--strict"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload[0]["name"] == "claude-code"
    assert payload[0]["status"] == "missing"

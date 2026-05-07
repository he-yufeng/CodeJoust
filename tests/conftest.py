import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "demo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "app.py").write_text("print('hi')\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    return repo


@pytest.fixture()
def fake_bin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Drop fake agent shims on PATH that edit a file and exit 0."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    _write_shim(
        bin_dir,
        "claude",
        """
from pathlib import Path

Path("app.py").open("a", encoding="utf-8").write("fake claude edit\\n")
print('{"type":"result","usage":{"input_tokens":1200,"output_tokens":300},"total_cost_usd":0.0042}')
""",
    )

    _write_shim(
        bin_dir,
        "aider",
        """
from pathlib import Path

Path("app.py").open("a", encoding="utf-8").write("fake aider line\\n")
print("Tokens: 1.1k sent, 210 received.")
print("Cost: $0.0021 message, $0.0021 session.")
""",
    )

    _write_shim(
        bin_dir,
        "codex",
        """
from pathlib import Path

Path("app.py").open("a", encoding="utf-8").write("fake codex line\\n")
print('{"timestamp":"2026-04-25T10:00:00Z","type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":800,"output_tokens":150,"total_tokens":950}}}}')
""",
    )

    _write_shim(
        bin_dir,
        "gemini",
        """
from pathlib import Path

Path("app.py").open("a", encoding="utf-8").write("fake gemini line\\n")
print('{"type":"init","session_id":"abc"}')
print('{"type":"message","role":"assistant","content":"done"}')
print('{"type":"result","status":"success","stats":{"input_tokens":640,"output_tokens":120,"total_tokens":760,"duration_ms":1100}}')
""",
    )

    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return bin_dir


def _write_shim(bin_dir: Path, name: str, source: str) -> None:
    script = bin_dir / f"{name}.py"
    script.write_text(source.lstrip(), encoding="utf-8")

    if os.name == "nt":
        shim = bin_dir / f"{name}.cmd"
        shim.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
        return

    shim = bin_dir / name
    shim.write_text(f'#!/usr/bin/env sh\nexec "{sys.executable}" "{script}" "$@"\n')
    shim.chmod(0o755)

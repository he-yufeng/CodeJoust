import os
import subprocess
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
    """Drop fake `claude` and `aider` shims on PATH that edit a file and exit 0."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    claude = bin_dir / "claude"
    claude.write_text(
        '#!/usr/bin/env bash\n'
        'set -e\n'
        'echo "fake claude edit" >> app.py\n'
        'printf \'%s\\n\' \'{"type":"result","usage":{"input_tokens":1200,"output_tokens":300},"total_cost_usd":0.0042}\'\n'
    )
    claude.chmod(0o755)

    aider = bin_dir / "aider"
    aider.write_text(
        '#!/usr/bin/env bash\n'
        'set -e\n'
        'echo "fake aider line" >> app.py\n'
        "printf '%s\\n' 'Tokens: 1.1k sent, 210 received.'\n"
        "printf '%s\\n' 'Cost: $0.0021 message, $0.0021 session.'\n"
    )
    aider.chmod(0o755)

    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    return bin_dir

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


def _git(args: list[str], cwd: Path) -> str:
    res = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        raise GitError(f"git {' '.join(args)} -> {res.returncode}: {res.stderr.strip()}")
    return res.stdout


def ensure_git_repo(repo_root: Path) -> None:
    if not (repo_root / ".git").exists():
        raise GitError(f"not a git repo: {repo_root}")


def current_branch(repo_root: Path) -> str:
    return _git(["rev-parse", "--abbrev-ref", "HEAD"], repo_root).strip()


def head_commit(repo_root: Path) -> str:
    return _git(["rev-parse", "HEAD"], repo_root).strip()


_JUNK_SEGMENTS = (
    "__pycache__/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".mypy_cache/",
    "node_modules/",
    ".venv/",
    "venv/",
    "dist/",
    "build/",
    ".codejoust/",
)
_JUNK_SUFFIXES = (".pyc", ".pyo", ".egg-info")


def _is_junk(path: str) -> bool:
    norm = path.lstrip("./")
    if any(seg in norm + "/" for seg in _JUNK_SEGMENTS):
        return True
    if any(norm.endswith(suf) for suf in _JUNK_SUFFIXES):
        return True
    if norm.endswith(".DS_Store"):
        return True
    return False


def add_worktree(repo_root: Path, path: Path, branch: str, base_commit: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _git(["worktree", "add", "-b", branch, str(path), base_commit], repo_root)


def remove_worktree(repo_root: Path, path: Path, branch: str | None = None) -> None:
    # Best effort cleanup. We don't want a prior failed run to block a re-run.
    try:
        _git(["worktree", "remove", "--force", str(path)], repo_root)
    except GitError:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    if branch:
        try:
            _git(["branch", "-D", branch], repo_root)
        except GitError:
            pass


def diff_against(repo_root: Path, worktree: Path, base_commit: str) -> tuple[str, int, int, int]:
    """Returns (unified_diff, files_changed, lines_added, lines_removed) for the worktree vs base."""
    # Include untracked files so newly-created files show up in the diff,
    # but filter out caches/build artefacts that tests and tooling drop in
    # — otherwise pytest's __pycache__ ends up in every agent's patch.
    raw = _git(
        ["-C", str(worktree), "ls-files", "--others", "--exclude-standard"],
        repo_root,
    ).strip().splitlines()
    untracked = [p for p in raw if p and not _is_junk(p)]
    if untracked:
        _git(["-C", str(worktree), "add", "--intent-to-add", "--", *untracked], repo_root)

    # Pathspec excludes keep generated files out of `git diff` even if they
    # were already tracked upstream.
    pathspec_excludes = [f":(exclude){seg.rstrip('/')}" for seg in _JUNK_SEGMENTS]
    pathspec_excludes += [f":(exclude)*{suf}" for suf in _JUNK_SUFFIXES]

    diff = _git(
        ["-C", str(worktree), "diff", base_commit, "--", ".", *pathspec_excludes],
        repo_root,
    )
    stat_line = _git(
        ["-C", str(worktree), "diff", "--shortstat", base_commit, "--", ".", *pathspec_excludes],
        repo_root,
    ).strip()

    files_changed = lines_added = lines_removed = 0
    if stat_line:
        # "3 files changed, 42 insertions(+), 5 deletions(-)"
        parts = [p.strip() for p in stat_line.split(",")]
        for p in parts:
            if "file" in p:
                files_changed = _first_int(p)
            elif "insertion" in p:
                lines_added = _first_int(p)
            elif "deletion" in p:
                lines_removed = _first_int(p)
    return diff, files_changed, lines_added, lines_removed


def _first_int(s: str) -> int:
    num = ""
    for ch in s:
        if ch.isdigit():
            num += ch
        elif num:
            break
    return int(num) if num else 0

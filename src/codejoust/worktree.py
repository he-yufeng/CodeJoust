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
    # Include untracked files so newly-created files show up in the diff.
    untracked = _git(
        ["-C", str(worktree), "ls-files", "--others", "--exclude-standard"],
        repo_root,
    ).strip().splitlines()
    if untracked:
        _git(["-C", str(worktree), "add", "--intent-to-add", "--", *untracked], repo_root)

    diff = _git(["-C", str(worktree), "diff", base_commit], repo_root)
    stat_line = _git(
        ["-C", str(worktree), "diff", "--shortstat", base_commit],
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

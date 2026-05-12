from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from codejoust.core import AgentSpec

CONFIG_NAMES = ("codejoust.yaml", "codejoust.yml", ".codejoust.yaml", ".codejoust.yml")


@dataclass(frozen=True)
class ProjectConfig:
    path: Path | None = None
    agents: list[AgentSpec] | None = None
    test_command: str | None = None
    timeout_s: int | None = None
    model: str | None = None
    keep_worktrees: bool | None = None
    html: bool | None = None


def load_project_config(repo: Path, explicit: Path | None = None) -> ProjectConfig:
    path = explicit or _find_config(repo)
    if path is None:
        return ProjectConfig()
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top-level config must be a mapping")

    return ProjectConfig(
        path=path,
        agents=_parse_agents(raw.get("agents"), path),
        test_command=_str_or_none(raw.get("test") or raw.get("test_command")),
        timeout_s=_int_or_none(raw.get("timeout") or raw.get("timeout_s"), path, "timeout"),
        model=_str_or_none(raw.get("model")),
        keep_worktrees=_bool_or_none(raw.get("keep_worktrees"), path, "keep_worktrees"),
        html=_bool_or_none(raw.get("html"), path, "html"),
    )


def _find_config(repo: Path) -> Path | None:
    for name in CONFIG_NAMES:
        path = repo / name
        if path.exists():
            return path
    return None


def _parse_agents(raw: Any, path: Path) -> list[AgentSpec] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        return [AgentSpec(name=name, cli="") for name in _split_agents(raw)]
    if not isinstance(raw, list):
        raise ValueError(f"{path}: agents must be a string or list")

    out: list[AgentSpec] = []
    for item in raw:
        if isinstance(item, str):
            out.append(AgentSpec(name=item, cli=""))
            continue
        if not isinstance(item, dict):
            raise ValueError(f"{path}: each agent must be a string or mapping")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{path}: agent mappings need a non-empty name")
        extra_args = item.get("extra_args") or []
        env = item.get("env") or {}
        if not isinstance(extra_args, list) or not all(isinstance(v, str) for v in extra_args):
            raise ValueError(f"{path}: agent {name} extra_args must be a list of strings")
        if not isinstance(env, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in env.items()
        ):
            raise ValueError(f"{path}: agent {name} env must be a string map")
        out.append(
            AgentSpec(
                name=name,
                cli=str(item.get("cli") or ""),
                model=_str_or_none(item.get("model")),
                extra_args=extra_args,
                env=env,
            )
        )
    return out


def _split_agents(value: str) -> list[str]:
    return [name.strip() for name in value.split(",") if name.strip()]


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _int_or_none(value: Any, path: Path, key: str) -> int | None:
    if value is None:
        return None
    try:
        out = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path}: {key} must be an integer") from exc
    if out <= 0:
        raise ValueError(f"{path}: {key} must be positive")
    return out


def _bool_or_none(value: Any, path: Path, key: str) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise ValueError(f"{path}: {key} must be true or false")

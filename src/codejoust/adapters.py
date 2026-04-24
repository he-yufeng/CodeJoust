from __future__ import annotations

import asyncio
import json
import os
import shutil
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional

from codejoust.core import AgentRun, AgentSpec


class AgentNotAvailable(RuntimeError):
    pass


class AgentAdapter(ABC):
    """Base class. Subclasses wrap one CLI (claude / aider / codex ...)."""

    name: str = ""
    default_cli: str = ""

    def __init__(self, spec: AgentSpec):
        self.spec = spec

    def resolved_cli(self) -> str:
        return self.spec.cli or self.default_cli

    def check(self) -> None:
        cli = self.resolved_cli()
        if shutil.which(cli) is None:
            raise AgentNotAvailable(
                f"{self.name}: '{cli}' not found on PATH. install it or pass --cli /path/to/{cli}"
            )

    @abstractmethod
    def build_command(self, task: str, cwd: Path) -> list[str]: ...

    def build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update(self.spec.env)
        return env

    async def run(
        self,
        task: str,
        cwd: Path,
        run: AgentRun,
        timeout_s: float,
        log_dir: Path,
    ) -> AgentRun:
        log_dir.mkdir(parents=True, exist_ok=True)
        run.stdout_path = log_dir / f"{self.name}.stdout.log"
        run.stderr_path = log_dir / f"{self.name}.stderr.log"

        run.status = "running"
        run.started_at = datetime.now()

        cmd = self.build_command(task, cwd)
        env = self.build_env()

        try:
            with open(run.stdout_path, "wb") as out_f, open(run.stderr_path, "wb") as err_f:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=str(cwd),
                    env=env,
                    stdout=out_f,
                    stderr=err_f,
                )
                try:
                    await asyncio.wait_for(proc.wait(), timeout=timeout_s)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    run.status = "timeout"
                    run.error = f"exceeded {timeout_s:.0f}s timeout"
                    return run

            if proc.returncode != 0:
                run.status = "error"
                run.error = f"exit code {proc.returncode}"
                return run

            self.parse_usage(run)
            run.status = "success"
        except FileNotFoundError as e:
            run.status = "error"
            run.error = str(e)
        finally:
            run.finished_at = datetime.now()
        return run

    def parse_usage(self, run: AgentRun) -> None:
        """Walk the agent's stdout JSONL and pull out token counts / cost.

        Each adapter has its own flavour. Default is a no-op; subclasses override.
        """
        return


class ClaudeCodeAdapter(AgentAdapter):
    name = "claude-code"
    default_cli = "claude"

    def build_command(self, task: str, cwd: Path) -> list[str]:
        cmd = [
            self.resolved_cli(),
            "-p",
            task,
            "--output-format",
            "stream-json",
            "--verbose",
            "--permission-mode",
            "bypassPermissions",
        ]
        if self.spec.model:
            cmd += ["--model", self.spec.model]
        cmd += list(self.spec.extra_args)
        return cmd

    def parse_usage(self, run: AgentRun) -> None:
        if not run.stdout_path or not run.stdout_path.exists():
            return
        in_tokens = 0
        out_tokens = 0
        cost = 0.0
        with open(run.stdout_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # The `result` event at the end carries a usage block with
                # aggregated tokens. Earlier assistant events also have usage
                # but we only want the final totals.
                if msg.get("type") == "result":
                    usage = msg.get("usage") or {}
                    in_tokens = usage.get("input_tokens", in_tokens)
                    out_tokens = usage.get("output_tokens", out_tokens)
                    cost = msg.get("total_cost_usd", cost) or cost
        run.input_tokens = in_tokens
        run.output_tokens = out_tokens
        run.cost_usd = float(cost or 0.0)


class AiderAdapter(AgentAdapter):
    name = "aider"
    default_cli = "aider"

    def build_command(self, task: str, cwd: Path) -> list[str]:
        cmd = [
            self.resolved_cli(),
            "--message",
            task,
            "--yes-always",
            "--no-auto-commits",
            "--no-pretty",
            "--no-stream",
        ]
        if self.spec.model:
            cmd += ["--model", self.spec.model]
        cmd += list(self.spec.extra_args)
        return cmd

    def parse_usage(self, run: AgentRun) -> None:
        # Aider prints "Tokens: 1.8k sent, 240 received." + "Cost: $0.01 message, $0.01 session."
        # We scrape the last occurrence — intermediate lines show running totals.
        if not run.stdout_path or not run.stdout_path.exists():
            return
        last_tokens_line: Optional[str] = None
        last_cost_line: Optional[str] = None
        with open(run.stdout_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.lstrip().startswith("Tokens:"):
                    last_tokens_line = line.strip()
                elif line.lstrip().startswith("Cost:"):
                    last_cost_line = line.strip()

        if last_tokens_line:
            run.input_tokens = _parse_aider_number(last_tokens_line, "sent")
            run.output_tokens = _parse_aider_number(last_tokens_line, "received")
        if last_cost_line:
            run.cost_usd = _parse_aider_cost(last_cost_line)


def _parse_aider_number(line: str, tag: str) -> int:
    tokens = line.replace(",", " ").split()
    for i, tok in enumerate(tokens):
        if tok.startswith(tag):
            # Number sits just before `tag`.
            if i == 0:
                return 0
            raw = tokens[i - 1].rstrip(",").lower()
            try:
                if raw.endswith("k"):
                    return int(float(raw[:-1]) * 1000)
                return int(float(raw))
            except ValueError:
                return 0
    return 0


def _parse_aider_cost(line: str) -> float:
    # "Cost: $0.02 message, $0.02 session."
    for part in line.split("$")[1:]:
        head = part.split()[0] if part.split() else ""
        try:
            return float(head.rstrip(",."))
        except ValueError:
            continue
    return 0.0


REGISTRY: dict[str, type[AgentAdapter]] = {
    "claude-code": ClaudeCodeAdapter,
    "claude": ClaudeCodeAdapter,
    "aider": AiderAdapter,
}


def build_adapter(spec: AgentSpec) -> AgentAdapter:
    key = spec.name.lower()
    if key not in REGISTRY:
        raise ValueError(f"unknown agent '{spec.name}'. known: {sorted(REGISTRY)}")
    return REGISTRY[key](spec)

from __future__ import annotations

from dataclasses import asdict, dataclass

from codejoust.adapters import REGISTRY, AgentNotAvailable, build_adapter
from codejoust.core import AgentSpec


@dataclass(frozen=True)
class AgentCheck:
    name: str
    cli: str
    status: str
    path: str | None = None
    note: str = ""

    @property
    def available(self) -> bool:
        return self.status == "ok"

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


def known_agent_names() -> list[str]:
    seen: set[type] = set()
    names: list[str] = []
    for cls in REGISTRY.values():
        if cls in seen:
            continue
        seen.add(cls)
        names.append(cls.name)
    return names


def check_agents(names: list[str] | None = None) -> list[AgentCheck]:
    checks: list[AgentCheck] = []
    seen: set[str] = set()

    for raw_name in names or known_agent_names():
        adapter = build_adapter(AgentSpec(name=raw_name, cli=""))
        if adapter.name in seen:
            continue
        seen.add(adapter.name)

        try:
            adapter.check()
        except AgentNotAvailable as exc:
            checks.append(
                AgentCheck(
                    name=adapter.name,
                    cli=adapter.resolved_cli(),
                    status="missing",
                    note=str(exc),
                )
            )
            continue

        checks.append(
            AgentCheck(
                name=adapter.name,
                cli=adapter.resolved_cli(),
                status="ok",
                path=adapter.executable(),
            )
        )

    return checks

"""Trusted connector registry (update.md §13).

Only reviewed connectors may be enabled. Arbitrary user MCP servers
are never executable by default. Each connector declares scopes;
expanding scopes requires fresh consent (guardrail approval).
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Connector:
    name: str
    scopes: tuple[str, ...]
    enabled: bool = False  # disabled until OAuth consent flow lands


REGISTRY: dict[str, Connector] = {
    "github-readonly": Connector("github-readonly", ("repo:read",)),
    "zotero": Connector("zotero", ("library:read", "library:write")),
    "google-drive": Connector("google-drive", ("drive:files:read",)),
}


def get_connector(name: str) -> Connector | None:
    return REGISTRY.get(name)


def enabled_connectors() -> list[Connector]:
    return [c for c in REGISTRY.values() if c.enabled]

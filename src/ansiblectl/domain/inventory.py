"""Typed inventory contracts and deterministic source merging."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from ansiblectl.domain.errors import DomainError


class InventoryError(DomainError):
    """Raised when an inventory source cannot produce valid hosts or groups."""


@dataclass(frozen=True)
class Host:
    name: str
    address: str
    variables: Mapping[str, object]
    source: str


@dataclass(frozen=True)
class InventoryFragment:
    source: str
    hosts: Mapping[str, Host]
    groups: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class ResolvedInventory:
    hosts: Mapping[str, Host]
    groups: Mapping[str, tuple[str, ...]]
    provenance: Mapping[str, str]
    diagnostics: tuple[str, ...]

    def canonical(self) -> dict[str, object]:
        """Return the stable generated representation for an execution adapter."""

        return {
            "hosts": {
                name: {"address": host.address, "variables": dict(host.variables)}
                for name, host in sorted(self.hosts.items())
            },
            "groups": {name: list(hosts) for name, hosts in sorted(self.groups.items())},
        }


class InventoryProvider(Protocol):
    def load(self) -> InventoryFragment:
        """Load one validated source fragment."""


def canonical_inventory_digest(inventory: Mapping[str, object]) -> str:
    """Return a stable digest of the exact canonical execution representation."""

    serialized = json.dumps(inventory, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"sha256:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"


def resolve_inventory(providers: list[InventoryProvider]) -> ResolvedInventory:
    """Merge low-to-high precedence providers; later host definitions win safely."""

    hosts: dict[str, Host] = {}
    groups: dict[str, tuple[str, ...]] = {}
    provenance: dict[str, str] = {}
    diagnostics: list[str] = []
    for provider in providers:
        fragment = provider.load()
        for name, host in fragment.hosts.items():
            if not name or not host.address:
                raise InventoryError(
                    f"Invalid host '{name}' from {fragment.source}. "
                    "Provide a host name and address."
                )
            if name in hosts:
                diagnostics.append(
                    f"Host '{name}' from {fragment.source} overrides {provenance[name]} "
                    "by precedence."
                )
            hosts[name] = host
            provenance[name] = fragment.source
        for group, members in fragment.groups.items():
            if not group or any(member not in hosts for member in members):
                raise InventoryError(
                    f"Invalid group '{group}' from {fragment.source}. "
                    "Reference resolved host names only."
                )
            groups[group] = members
    return ResolvedInventory(hosts, groups, provenance, tuple(diagnostics))

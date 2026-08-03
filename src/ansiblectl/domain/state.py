"""Typed workspace-state contracts."""

from dataclasses import dataclass
from typing import Protocol

from ansiblectl.domain.errors import StateError


@dataclass(frozen=True)
class CacheEntry:
    """One cache value with explicit source and invalidation metadata."""

    source_identity: str
    invalidation_condition: str
    value: dict[str, object]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_identity, str)
            or not self.source_identity.strip()
            or not isinstance(self.invalidation_condition, str)
            or not self.invalidation_condition.strip()
            or not isinstance(self.value, dict)
        ):
            raise StateError("Cache entry metadata and value types are invalid.")


class StatePort(Protocol):
    """Read and atomically replace workspace-scoped cache entries."""

    def read(self) -> dict[str, CacheEntry]: ...

    def write(self, entries: dict[str, CacheEntry]) -> None: ...

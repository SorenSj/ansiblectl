"""Safe workspace-state inspection use case."""

from dataclasses import dataclass

from ansiblectl.domain.state import StateInvalidationResult, StatePort


@dataclass(frozen=True)
class CacheEntrySummary:
    """Non-value cache metadata safe for operator inspection."""

    name: str
    source_identity: str
    invalidation_condition: str


@dataclass(frozen=True)
class StateService:
    """Inspect cache metadata without exposing stored values."""

    port: StatePort

    def inspect(self) -> tuple[CacheEntrySummary, ...]:
        entries = self.port.read()
        return tuple(
            CacheEntrySummary(name, entry.source_identity, entry.invalidation_condition)
            for name, entry in sorted(entries.items())
        )

    def invalidate(self, name: str, *, apply: bool = False) -> StateInvalidationResult:
        """Preview or apply invalidation of one exact named cache entry."""

        return self.port.invalidate(name, apply=apply)

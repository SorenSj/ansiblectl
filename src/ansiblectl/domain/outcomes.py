"""Typed application outcomes for delivery adapters."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class OutcomeKind(StrEnum):
    SUCCESS = "success"
    VALIDATION_FAILURE = "validation_failure"
    OPERATIONAL_FAILURE = "operational_failure"
    CANCELLED = "cancelled"
    UNEXPECTED_FAILURE = "unexpected_failure"


@dataclass(frozen=True)
class CommandOutcome:
    """A safe result returned by application services and rendered only by the CLI."""

    kind: OutcomeKind
    operation: str
    data: Mapping[str, object] | None = None
    reason: str | None = None
    remediation: str | None = None

    @property
    def is_success(self) -> bool:
        return self.kind is OutcomeKind.SUCCESS

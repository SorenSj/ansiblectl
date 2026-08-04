"""Transport-neutral contracts for bounded durable event delivery."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from ansiblectl.domain.durable_events import DurableEventClaim, DurableEventEnvelope

_REASON_CODE_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{0,63}")


class DeliveryOutcomeState(StrEnum):
    """Typed outcome returned by one injected delivery adapter."""

    DELIVERED = "delivered"
    FAILED = "failed"


class DeliveryRunState(StrEnum):
    """Stable state of one bounded runner invocation."""

    DELIVERED = "delivered"
    FAILED = "failed"
    IDLE = "idle"


@dataclass(frozen=True)
class DeliveryOutcome:
    """Adapter result containing no transport detail."""

    state: DeliveryOutcomeState
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if self.state is DeliveryOutcomeState.DELIVERED and self.failure_reason is not None:
            raise ValueError("Delivered event outcome cannot contain a failure reason.")
        if self.state is DeliveryOutcomeState.FAILED:
            validate_failure_reason(self.failure_reason)

    @classmethod
    def success(cls) -> DeliveryOutcome:
        return cls(DeliveryOutcomeState.DELIVERED)

    @classmethod
    def failure(cls, reason_code: str) -> DeliveryOutcome:
        return cls(DeliveryOutcomeState.FAILED, reason_code)


@dataclass(frozen=True)
class DeliveryRetryProfile:
    """Immutable deterministic retry and lease configuration."""

    max_attempts: int
    retry_delays: tuple[int, ...]
    lease_seconds: int

    def __post_init__(self) -> None:
        for value, label in (
            (self.max_attempts, "maximum attempts"),
            (self.lease_seconds, "lease seconds"),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"Delivery {label} must be a positive integer.")
        if not self.retry_delays or any(
            not isinstance(delay, int) or isinstance(delay, bool) or delay < 1
            for delay in self.retry_delays
        ):
            raise ValueError("Delivery retry delays must be positive integer seconds.")


@dataclass(frozen=True)
class DeliveryRunResult:
    """Versioned payload-free summary of one runner invocation."""

    consumer_id: str
    state: DeliveryRunState
    delivered_count: int
    failed_count: int
    last_event_id: str | None
    last_sequence: int | None
    failure_reason: str | None
    schema_version: int = 1

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "consumer_id": self.consumer_id,
            "state": self.state.value,
            "delivered_count": self.delivered_count,
            "failed_count": self.failed_count,
            "last_event_id": self.last_event_id,
            "last_sequence": self.last_sequence,
            "failure_reason": self.failure_reason,
        }


class EventDeliveryAdapterPort(Protocol):
    """Deliver one already-redacted immutable envelope."""

    def deliver(self, envelope: DurableEventEnvelope) -> DeliveryOutcome: ...


class DurableEventDeliveryStore(Protocol):
    """Minimal durable consumer operations required by the runner."""

    def claim_next(
        self,
        consumer_id: str,
        *,
        lease_seconds: int = 30,
        now: datetime | None = None,
        claim_token: str | None = None,
    ) -> DurableEventClaim | None: ...

    def acknowledge(
        self,
        consumer_id: str,
        *,
        sequence: int,
        event_id: str,
        claim_token: str,
    ) -> None: ...

    def record_failure(
        self,
        consumer_id: str,
        *,
        sequence: int,
        event_id: str,
        claim_token: str,
        reason_code: str,
        retry_delays: tuple[int, ...],
        max_attempts: int,
        now: datetime | None = None,
    ) -> None: ...


def validate_failure_reason(reason_code: object) -> str:
    if not isinstance(reason_code, str) or not _REASON_CODE_PATTERN.fullmatch(reason_code):
        raise ValueError("Delivery failure reason is not canonical.")
    return reason_code


__all__ = [
    "DeliveryOutcome",
    "DeliveryOutcomeState",
    "DeliveryRetryProfile",
    "DeliveryRunResult",
    "DeliveryRunState",
    "DurableEventDeliveryStore",
    "EventDeliveryAdapterPort",
    "validate_failure_reason",
]

"""Versioned immutable envelopes for durable public-event delivery."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ansiblectl.domain.events import PUBLIC_EVENTS

_ULID_PATTERN = re.compile(r"[0-7][0-9A-HJKMNP-TV-Z]{25}")
_UTC_TIMESTAMP_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z")
_CONSUMER_ID_PATTERN = re.compile(r"[a-z][a-z0-9._-]{0,127}")


@dataclass(frozen=True)
class DurableEventEnvelope:
    """One canonical redacted event committed to the workspace outbox."""

    event_id: str
    sequence: int
    name: str
    occurred_at: str
    operation_id: str | None
    payload: Mapping[str, object]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Durable event schema version must be 1.")
        if not isinstance(self.event_id, str) or not _ULID_PATTERN.fullmatch(self.event_id):
            raise ValueError("Durable event ID must be a canonical ULID.")
        if (
            not isinstance(self.sequence, int)
            or isinstance(self.sequence, bool)
            or self.sequence < 1
        ):
            raise ValueError("Durable event sequence must be a positive integer.")
        if self.name not in PUBLIC_EVENTS:
            raise ValueError("Durable event name must be a documented public event.")
        if not isinstance(self.occurred_at, str) or not _UTC_TIMESTAMP_PATTERN.fullmatch(
            self.occurred_at
        ):
            raise ValueError("Durable event timestamp must be canonical UTC with microseconds.")
        if self.operation_id is not None and (
            not isinstance(self.operation_id, str) or not _ULID_PATTERN.fullmatch(self.operation_id)
        ):
            raise ValueError("Durable event operation ID must be a canonical ULID or null.")
        if not isinstance(self.payload, Mapping):
            raise ValueError("Durable event payload must be a string-keyed mapping.")
        frozen_payload = _freeze_json(self.payload)
        assert isinstance(frozen_payload, Mapping)
        object.__setattr__(self, "payload", frozen_payload)

    def to_payload(self) -> dict[str, object]:
        """Return the complete schema representation."""

        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "sequence": self.sequence,
            "name": self.name,
            "occurred_at": self.occurred_at,
            "operation_id": self.operation_id,
            "payload": _thaw_json(self.payload),
        }


@dataclass(frozen=True)
class DurableEventClaim:
    """One time-bounded right to acknowledge a consumer's next event."""

    consumer_id: str
    claim_token: str
    lease_expires_at: str
    envelope: DurableEventEnvelope

    def __post_init__(self) -> None:
        validate_consumer_id(self.consumer_id)
        if not isinstance(self.claim_token, str) or not _ULID_PATTERN.fullmatch(self.claim_token):
            raise ValueError("Durable event claim token must be a canonical ULID.")
        if not isinstance(self.lease_expires_at, str) or not _UTC_TIMESTAMP_PATTERN.fullmatch(
            self.lease_expires_at
        ):
            raise ValueError("Durable event claim expiry must be canonical UTC with microseconds.")
        if not isinstance(self.envelope, DurableEventEnvelope):
            raise ValueError("Durable event claim must contain an event envelope.")


def validate_consumer_id(consumer_id: object) -> str:
    """Return a canonical public consumer identifier or reject it."""

    if not isinstance(consumer_id, str) or not _CONSUMER_ID_PATTERN.fullmatch(consumer_id):
        raise ValueError("Durable event consumer ID is not canonical.")
    return consumer_id


def _freeze_json(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Durable event payload numbers must be finite.")
        return value
    if isinstance(value, Mapping):
        if not all(isinstance(name, str) for name in value):
            raise ValueError("Durable event payload keys must be strings.")
        return MappingProxyType({name: _freeze_json(item) for name, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    raise ValueError("Durable event payload values must use JSON-compatible types.")


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {name: _thaw_json(item) for name, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


__all__ = ["DurableEventClaim", "DurableEventEnvelope", "validate_consumer_id"]

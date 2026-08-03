"""Structured, redacted log event contract."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

_SENSITIVE = {"secret", "token", "password", "credential", "key"}


@dataclass(frozen=True)
class LogEvent:
    level: str
    name: str
    fields: Mapping[str, object] = field(default_factory=dict)
    correlation_id: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def redacted(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "event": self.name,
            "correlation_id": self.correlation_id,
            "fields": _redact(self.fields),
        }


class LogSink(Protocol):
    def emit(self, record: Mapping[str, object]) -> None: ...


def emit(sink: LogSink, event: LogEvent) -> None:
    """Deliver a redacted record, never raw event fields, to a configured sink."""

    sink.emit(event.redacted())


def _redact(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: "<redacted>" if key.lower() in _SENSITIVE else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value

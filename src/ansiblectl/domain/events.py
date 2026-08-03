"""Typed public events with safe payload redaction."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

PUBLIC_EVENTS = {"execution.completed", "workspace.initialized"}
_SENSITIVE = {"secret", "token", "password", "credential", "key"}


@dataclass(frozen=True)
class Event:
    name: str
    payload: Mapping[str, object]

    def __post_init__(self) -> None:
        if self.name not in PUBLIC_EVENTS:
            raise ValueError(f"Undocumented event '{self.name}'.")

    def safe_payload(self) -> dict[str, object]:
        return _redact(self.payload)


Subscriber = Callable[[Event], None]


@dataclass
class EventBus:
    subscribers: list[Subscriber] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)

    def publish(self, event: Event) -> None:
        safe_event = Event(event.name, event.safe_payload())
        for subscriber in self.subscribers:
            try:
                subscriber(safe_event)
            except Exception as error:
                self.diagnostics.append(
                    f"Subscriber failed for {event.name}: {error.__class__.__name__}."
                )


def _redact(value: object) -> dict[str, object]:
    assert isinstance(value, Mapping)
    return {
        key: "<redacted>" if key.lower() in _SENSITIVE else _redact_item(item)
        for key, item in value.items()
    }


def _redact_item(value: object) -> object:
    if isinstance(value, Mapping):
        return _redact(value)
    if isinstance(value, list):
        return [_redact_item(item) for item in value]
    return value

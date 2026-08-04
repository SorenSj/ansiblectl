"""Typed public events with safe payload redaction."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from ansiblectl.domain.redaction import redact

PUBLIC_EVENTS = {
    "event.delivery.abandoned",
    "execution.completed",
    "workspace.initialized",
}


@dataclass(frozen=True)
class Event:
    name: str
    payload: Mapping[str, object]

    def __post_init__(self) -> None:
        if self.name not in PUBLIC_EVENTS:
            raise ValueError(f"Undocumented event '{self.name}'.")

    def safe_payload(self) -> dict[str, object]:
        safe_payload = redact(self.payload)
        assert isinstance(safe_payload, dict)
        return safe_payload


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

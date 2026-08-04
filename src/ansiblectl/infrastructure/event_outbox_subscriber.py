"""In-process subscriber that hands safe public events to the durable outbox."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ansiblectl.domain.events import Event
from ansiblectl.infrastructure.event_outbox import SqliteEventOutbox


@dataclass(frozen=True)
class EventOutboxSubscriber:
    """Append an already published event without changing EventBus semantics."""

    outbox: SqliteEventOutbox

    def __call__(self, event: Event) -> None:
        durable_event = Event(event.name, {}) if event.name == "workspace.initialized" else event
        self.outbox.append(durable_event)


@dataclass(frozen=True)
class WorkspaceEventOutboxSubscriber:
    """Select a newly initialized workspace without persisting its absolute path."""

    def __call__(self, event: Event) -> None:
        workspace = event.payload.get("workspace")
        if event.name != "workspace.initialized" or not isinstance(workspace, str):
            raise ValueError("Workspace initialization event is invalid.")
        EventOutboxSubscriber(SqliteEventOutbox(Path(workspace)))(event)


__all__ = ["EventOutboxSubscriber", "WorkspaceEventOutboxSubscriber"]

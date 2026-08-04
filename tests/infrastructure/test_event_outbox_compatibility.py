"""Compatibility tests for durable and existing in-process event consumers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ansiblectl.domain.events import Event, EventBus
from ansiblectl.infrastructure.event_outbox import SqliteEventOutbox
from ansiblectl.infrastructure.event_outbox_subscriber import EventOutboxSubscriber
from ansiblectl.infrastructure.execution_history import JsonLinesExecutionHistory
from ansiblectl.infrastructure.json_logging import EventLogSubscriber, JsonLinesLogSink

_NOW = datetime(2026, 8, 4, tzinfo=UTC)
_TOKENS = (
    "00000000Z90000000000000000",
    "00000000ZA0000000000000000",
)


def _execution_event(execution_id: str) -> Event:
    return Event(
        "execution.completed",
        {
            "execution_id": execution_id,
            "status": "completed",
            "exit_code": 0,
            "elapsed_seconds": 1.0,
            "token": "must-not-persist",
        },
    )


def test_outbox_failure_preserves_existing_subscriber_delivery(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    event_directory = tmp_path / ".ansiblectl/events"
    event_directory.parent.mkdir()
    event_directory.symlink_to(outside, target_is_directory=True)
    delivered: list[Event] = []
    bus = EventBus([EventOutboxSubscriber(SqliteEventOutbox(tmp_path)), delivered.append])
    event = Event("workspace.initialized", {"workspace": "safe"})

    bus.publish(event)

    assert delivered == [event]
    assert bus.diagnostics == ["Subscriber failed for workspace.initialized: StateError."]
    assert list(outside.iterdir()) == []


def test_outbox_strips_workspace_path_without_changing_other_subscribers(tmp_path: Path) -> None:
    delivered: list[Event] = []
    bus = EventBus([EventOutboxSubscriber(SqliteEventOutbox(tmp_path)), delivered.append])
    event = Event("workspace.initialized", {"workspace": str(tmp_path)})

    bus.publish(event)

    assert delivered == [event]
    assert SqliteEventOutbox(tmp_path).read_all()[0].payload == {}


def test_history_and_outbox_retention_are_independent(tmp_path: Path) -> None:
    outbox = SqliteEventOutbox(tmp_path)
    history = JsonLinesExecutionHistory(tmp_path)
    bus = EventBus(
        [
            EventLogSubscriber(JsonLinesLogSink(tmp_path)),
            EventOutboxSubscriber(outbox),
        ]
    )
    bus.publish(_execution_event("run-1"))

    assert [record.execution_id for record in history.list()] == ["run-1"]
    assert outbox.read_all()[0].payload["token"] == "<redacted>"
    history.prune(0)
    assert history.list() == ()
    assert len(outbox.read_all()) == 1

    bus.publish(_execution_event("run-2"))
    history_before_retention = history.path.read_bytes()
    outbox.register_consumer("compatibility")
    for index in range(2):
        claim = outbox.claim_next("compatibility", now=_NOW, claim_token=_TOKENS[index])
        assert claim is not None
        outbox.acknowledge(
            "compatibility",
            sequence=claim.envelope.sequence,
            event_id=claim.envelope.event_id,
            claim_token=claim.claim_token,
        )

    result = outbox.retain(apply=True)

    assert result.event_count == 2
    assert outbox.read_all() == ()
    assert history.path.read_bytes() == history_before_retention
    assert [record.execution_id for record in history.list()] == ["run-2"]

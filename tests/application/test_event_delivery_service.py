"""Bounded durable event delivery service tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ansiblectl.application.event_delivery import ADAPTER_FAILURE, EventDeliveryService
from ansiblectl.domain.durable_events import DurableEventEnvelope
from ansiblectl.domain.errors import StateError
from ansiblectl.domain.event_delivery import (
    DeliveryOutcome,
    DeliveryRetryProfile,
    DeliveryRunState,
)
from ansiblectl.domain.events import Event
from ansiblectl.infrastructure.event_outbox import SqliteEventOutbox

_NOW = datetime(2026, 8, 4, tzinfo=UTC)
_PROFILE = DeliveryRetryProfile(3, (10, 30), 30)


@dataclass
class RecordingAdapter:
    outcomes: list[DeliveryOutcome]
    received: list[DurableEventEnvelope] = field(default_factory=list)

    def deliver(self, envelope: DurableEventEnvelope) -> DeliveryOutcome:
        self.received.append(envelope)
        return self.outcomes.pop(0)


@dataclass
class BrokenAdapter:
    calls: int = 0

    def deliver(self, envelope: DurableEventEnvelope) -> DeliveryOutcome:
        self.calls += 1
        raise RuntimeError("private endpoint response and credential")


def _outbox(tmp_path: Path, count: int = 2) -> SqliteEventOutbox:
    outbox = SqliteEventOutbox(tmp_path)
    for index in range(count):
        outbox.append(Event("workspace.initialized", {"index": index, "token": "private"}))
    outbox.register_consumer("adapter")
    return outbox


def test_step_acknowledges_delivered_event_then_becomes_idle(tmp_path: Path) -> None:
    outbox = _outbox(tmp_path, count=1)
    adapter = RecordingAdapter([DeliveryOutcome.success()])
    service = EventDeliveryService(outbox, adapter, _PROFILE, lambda: _NOW)

    delivered = service.step("adapter")
    idle = service.step("adapter")

    assert delivered.state is DeliveryRunState.DELIVERED
    assert delivered.delivered_count == 1
    assert delivered.last_event_id == adapter.received[0].event_id
    assert idle.state is DeliveryRunState.IDLE
    assert len(adapter.received) == 1


def test_bounded_batch_stops_when_idle_and_preserves_last_event_identity(
    tmp_path: Path,
) -> None:
    outbox = _outbox(tmp_path)
    adapter = RecordingAdapter([DeliveryOutcome.success(), DeliveryOutcome.success()])
    service = EventDeliveryService(outbox, adapter, _PROFILE, lambda: _NOW)

    result = service.run("adapter", max_events=5)

    assert result.state is DeliveryRunState.IDLE
    assert result.delivered_count == 2
    assert result.failed_count == 0
    assert result.last_event_id == adapter.received[-1].event_id
    assert result.last_sequence == 2


def test_failure_is_persisted_and_stops_bounded_batch(tmp_path: Path) -> None:
    outbox = _outbox(tmp_path)
    adapter = RecordingAdapter(
        [DeliveryOutcome.failure("TEMPORARY_UNAVAILABLE"), DeliveryOutcome.success()]
    )
    service = EventDeliveryService(outbox, adapter, _PROFILE, lambda: _NOW)

    result = service.run("adapter", max_events=2)

    assert result.state is DeliveryRunState.FAILED
    assert result.delivered_count == 0
    assert result.failed_count == 1
    assert result.failure_reason == "TEMPORARY_UNAVAILABLE"
    assert len(adapter.received) == 1
    status = outbox.inspect_consumers(now=_NOW)[0]
    assert status.state == "delayed"
    assert status.attempt_count == 1
    assert status.next_attempt_at == "2026-08-04T00:00:10.000000Z"


def test_adapter_exception_is_reduced_to_stable_reason(tmp_path: Path) -> None:
    outbox = _outbox(tmp_path, count=1)
    adapter = BrokenAdapter()
    service = EventDeliveryService(outbox, adapter, _PROFILE, lambda: _NOW)

    result = service.step("adapter")

    assert result.failure_reason == ADAPTER_FAILURE
    assert "private" not in str(result.to_payload())
    assert adapter.calls == 1


def test_invalid_adapter_result_is_reduced_to_stable_reason(tmp_path: Path) -> None:
    class InvalidAdapter:
        def deliver(self, envelope: DurableEventEnvelope) -> DeliveryOutcome:
            return object()  # type: ignore[return-value]

    result = EventDeliveryService(
        _outbox(tmp_path, count=1), InvalidAdapter(), _PROFILE, lambda: _NOW
    ).step("adapter")

    assert result.failure_reason == ADAPTER_FAILURE


def test_stale_completion_cannot_advance_reclaimed_event(tmp_path: Path) -> None:
    outbox = _outbox(tmp_path, count=1)

    class ReclaimingAdapter:
        def deliver(self, envelope: DurableEventEnvelope) -> DeliveryOutcome:
            replacement = outbox.claim_next("adapter", now=_NOW + timedelta(seconds=31))
            assert replacement is not None
            return DeliveryOutcome.success()

    service = EventDeliveryService(outbox, ReclaimingAdapter(), _PROFILE, lambda: _NOW)

    with pytest.raises(StateError, match="stale or invalid"):
        service.step("adapter")

    assert outbox.inspect_consumers(now=_NOW + timedelta(seconds=31))[0].state == "claimed"


@pytest.mark.parametrize("max_events", [0, -1, True])
def test_batch_requires_positive_integer_bound(tmp_path: Path, max_events: int) -> None:
    service = EventDeliveryService(
        _outbox(tmp_path, count=0), RecordingAdapter([]), _PROFILE, lambda: _NOW
    )

    with pytest.raises(ValueError, match="positive integer"):
        service.run("adapter", max_events=max_events)

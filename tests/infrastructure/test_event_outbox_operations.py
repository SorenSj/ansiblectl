"""Retry, recovery, inspection, and retention tests for durable events."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ansiblectl.domain.durable_events import DurableEventClaim
from ansiblectl.domain.errors import StateError
from ansiblectl.domain.events import Event
from ansiblectl.infrastructure.event_outbox import SqliteEventOutbox

_NOW = datetime(2026, 8, 4, tzinfo=UTC)
_EVENT_ID = "00000000Z80000000000000000"
_TOKENS = (
    "00000000Z90000000000000000",
    "00000000ZA0000000000000000",
    "00000000ZB0000000000000000",
    "00000000ZC0000000000000000",
)


def _claim(
    outbox: SqliteEventOutbox, *, now: datetime, token: str = _TOKENS[0]
) -> DurableEventClaim:
    claim = outbox.claim_next("adapter", now=now, claim_token=token)
    assert claim is not None
    return claim


def _fail(
    outbox: SqliteEventOutbox,
    *,
    now: datetime,
    token: str,
    max_attempts: int = 3,
) -> None:
    outbox.record_failure(
        "adapter",
        sequence=1,
        event_id=_EVENT_ID,
        claim_token=token,
        reason_code="TEMPORARY_UNAVAILABLE",
        retry_delays=(10, 30),
        max_attempts=max_attempts,
        now=now,
    )


def test_retry_schedule_is_deterministic_bounded_and_ordered(tmp_path: Path) -> None:
    outbox = SqliteEventOutbox(tmp_path)
    outbox.append(
        Event("workspace.initialized", {"token": "secret"}),
        event_id=_EVENT_ID,
        occurred_at="2026-08-04T00:00:00.000000Z",
    )
    outbox.append(Event("workspace.initialized", {"number": 2}))
    outbox.register_consumer("adapter")

    first = _claim(outbox, now=_NOW, token=_TOKENS[0])
    _fail(outbox, now=_NOW, token=first.claim_token)
    status = outbox.inspect_consumers(now=_NOW)[0]
    assert status.state == "delayed"
    assert status.pending_count == 2
    assert status.lowest_pending_sequence == 1
    assert status.attempt_count == 1
    assert status.next_attempt_at == "2026-08-04T00:00:10.000000Z"
    assert outbox.claim_next("adapter", now=_NOW + timedelta(seconds=9)) is None

    second = _claim(outbox, now=_NOW + timedelta(seconds=10), token=_TOKENS[1])
    _fail(outbox, now=_NOW + timedelta(seconds=10), token=second.claim_token)
    assert outbox.inspect_consumers(now=_NOW + timedelta(seconds=10))[0].next_attempt_at == (
        "2026-08-04T00:00:40.000000Z"
    )
    third = _claim(outbox, now=_NOW + timedelta(seconds=40), token=_TOKENS[2])
    _fail(outbox, now=_NOW + timedelta(seconds=40), token=third.claim_token)

    exhausted = outbox.inspect_consumers(now=_NOW + timedelta(days=1))[0]
    assert exhausted.state == "exhausted"
    assert exhausted.attempt_count == 3
    assert exhausted.next_attempt_at is None
    assert outbox.claim_next("adapter", now=_NOW + timedelta(days=1)) is None


def test_operator_retry_resets_only_exact_blocked_event(tmp_path: Path) -> None:
    outbox = SqliteEventOutbox(tmp_path)
    outbox.append(
        Event("workspace.initialized", {}),
        event_id=_EVENT_ID,
        occurred_at="2026-08-04T00:00:00.000000Z",
    )
    outbox.register_consumer("adapter")
    claim = _claim(outbox, now=_NOW)
    _fail(outbox, now=_NOW, token=claim.claim_token, max_attempts=1)

    with pytest.raises(StateError, match="does not match"):
        outbox.retry("adapter", sequence=1, event_id=_TOKENS[3])
    outbox.retry("adapter", sequence=1, event_id=_EVENT_ID)

    reset = outbox.inspect_consumers(now=_NOW)[0]
    assert reset.state == "pending"
    assert reset.attempt_count == 0
    assert _claim(outbox, now=_NOW, token=_TOKENS[1]).envelope.event_id == _EVENT_ID


def test_stale_failure_cannot_replace_current_claim(tmp_path: Path) -> None:
    outbox = SqliteEventOutbox(tmp_path)
    outbox.append(
        Event("workspace.initialized", {}),
        event_id=_EVENT_ID,
        occurred_at="2026-08-04T00:00:00.000000Z",
    )
    outbox.register_consumer("adapter")
    old = _claim(outbox, now=_NOW, token=_TOKENS[0])
    current = _claim(outbox, now=_NOW + timedelta(seconds=31), token=_TOKENS[1])

    with pytest.raises(StateError, match="stale or invalid"):
        _fail(outbox, now=_NOW + timedelta(seconds=31), token=old.claim_token)
    _fail(outbox, now=_NOW + timedelta(seconds=31), token=current.claim_token)


def test_abandon_previews_then_advances_and_appends_redacted_audit_event(
    tmp_path: Path,
) -> None:
    outbox = SqliteEventOutbox(tmp_path)
    original = outbox.append(
        Event("workspace.initialized", {"password": "private"}),
        event_id=_EVENT_ID,
        occurred_at="2026-08-04T00:00:00.000000Z",
    )
    outbox.register_consumer("adapter")
    claim = _claim(outbox, now=_NOW)
    _fail(outbox, now=_NOW, token=claim.claim_token, max_attempts=1)

    preview = outbox.abandon("adapter", sequence=1, event_id=_EVENT_ID)
    assert preview.applied is False
    assert outbox.inspect_consumers(now=_NOW)[0].state == "exhausted"
    assert outbox.read_all() == (original,)

    applied = outbox.abandon("adapter", sequence=1, event_id=_EVENT_ID, apply=True)
    assert applied.applied is True
    events = outbox.read_all()
    assert events[0] == original
    assert events[1].name == "event.delivery.abandoned"
    assert events[1].payload == {
        "consumer_id": "adapter",
        "event_id": _EVENT_ID,
        "sequence": 1,
    }
    assert outbox.inspect_consumers(now=_NOW)[0].lowest_pending_sequence == 2


def test_retention_uses_shared_prefix_previews_and_never_reuses_sequences(
    tmp_path: Path,
) -> None:
    outbox = SqliteEventOutbox(tmp_path)
    events = tuple(
        outbox.append(Event("workspace.initialized", {"number": number})) for number in range(3)
    )
    outbox.register_consumer("adapter")
    outbox.register_consumer("secondary")

    for consumer_id, count in (("adapter", 2), ("secondary", 1)):
        for index in range(count):
            claim = outbox.claim_next(consumer_id, now=_NOW, claim_token=_TOKENS[index])
            assert claim is not None
            outbox.acknowledge(
                consumer_id,
                sequence=claim.envelope.sequence,
                event_id=claim.envelope.event_id,
                claim_token=claim.claim_token,
            )

    preview = outbox.retain()
    assert preview.through_sequence == 1
    assert preview.event_count == 1
    assert preview.applied is False
    assert outbox.read_all() == events

    applied = outbox.retain(apply=True)
    assert applied.event_count == 1
    assert applied.applied is True
    assert outbox.read_all() == events[1:]
    assert outbox.append(Event("workspace.initialized", {})).sequence == 4


def test_retention_without_consumers_is_a_read_only_empty_plan(tmp_path: Path) -> None:
    outbox = SqliteEventOutbox(tmp_path)
    event = outbox.append(Event("workspace.initialized", {}))

    assert outbox.retain(apply=True).event_count == 0
    assert outbox.read_all() == (event,)


@pytest.mark.parametrize(
    ("reason_code", "retry_delays", "max_attempts"),
    [
        ("secret detail", (1,), 1),
        ("FAILED", (), 1),
        ("FAILED", (0,), 1),
        ("FAILED", (1,), 0),
    ],
)
def test_failure_policy_rejects_unstable_or_unbounded_values(
    tmp_path: Path,
    reason_code: str,
    retry_delays: tuple[int, ...],
    max_attempts: int,
) -> None:
    with pytest.raises(ValueError):
        SqliteEventOutbox(tmp_path).record_failure(
            "adapter",
            sequence=1,
            event_id=_EVENT_ID,
            claim_token=_TOKENS[0],
            reason_code=reason_code,
            retry_delays=retry_delays,
            max_attempts=max_attempts,
        )

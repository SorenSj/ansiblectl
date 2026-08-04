"""SQLite durable event outbox tests."""

import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ansiblectl.domain.errors import StateError
from ansiblectl.domain.events import Event
from ansiblectl.infrastructure.event_outbox import MAX_ENVELOPE_BYTES, SqliteEventOutbox

_EVENT_ID = "00000000Z80000000000000000"
_TIMESTAMP = "2026-08-04T00:00:00.000000Z"
_CLAIM_TOKEN_ONE = "00000000Z90000000000000000"
_CLAIM_TOKEN_TWO = "00000000ZA0000000000000000"


def test_append_is_redacted_immutable_and_owner_only(tmp_path: Path) -> None:
    outbox = SqliteEventOutbox(tmp_path)

    envelope = outbox.append(
        Event("execution.completed", {"execution_id": "one", "token": "hidden"}),
        event_id=_EVENT_ID,
        occurred_at=_TIMESTAMP,
    )

    assert envelope.sequence == 1
    assert envelope.payload == {"execution_id": "one", "token": "<redacted>"}
    assert outbox.read_all() == (envelope,)
    path = tmp_path / ".ansiblectl/events/outbox.sqlite3"
    assert os.stat(path).st_mode & 0o777 == 0o600
    with (
        closing(sqlite3.connect(path)) as connection,
        pytest.raises(sqlite3.IntegrityError, match="immutable"),
    ):
        connection.execute("UPDATE events SET name = 'workspace.initialized' WHERE sequence = 1")


def test_parallel_appends_allocate_unique_contiguous_sequences(tmp_path: Path) -> None:
    def append(index: int) -> int:
        envelope = SqliteEventOutbox(tmp_path).append(
            Event("workspace.initialized", {"index": index})
        )
        return envelope.sequence

    with ThreadPoolExecutor(max_workers=8) as executor:
        sequences = list(executor.map(append, range(24)))

    assert sorted(sequences) == list(range(1, 25))
    assert [event.sequence for event in SqliteEventOutbox(tmp_path).read_all()] == list(
        range(1, 25)
    )


def test_unknown_schema_is_preserved_and_rejected(tmp_path: Path) -> None:
    outbox = SqliteEventOutbox(tmp_path)
    outbox.append(Event("workspace.initialized", {}))
    path = tmp_path / ".ansiblectl/events/outbox.sqlite3"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA user_version = 99")

    with pytest.raises(StateError, match="schema is unsupported"):
        outbox.read_all()

    assert path.is_file()


def test_symlinked_outbox_is_rejected_without_touching_target(tmp_path: Path) -> None:
    target = tmp_path / "outside.sqlite3"
    target.write_bytes(b"evidence")
    directory = tmp_path / ".ansiblectl/events"
    directory.mkdir(parents=True)
    (directory / "outbox.sqlite3").symlink_to(target)

    with pytest.raises(StateError, match="regular non-symlink"):
        SqliteEventOutbox(tmp_path).append(Event("workspace.initialized", {}))

    assert target.read_bytes() == b"evidence"


def test_oversized_or_non_json_payload_rolls_back_without_consuming_sequence(
    tmp_path: Path,
) -> None:
    outbox = SqliteEventOutbox(tmp_path)
    with pytest.raises(StateError, match="could not be appended safely"):
        outbox.append(Event("workspace.initialized", {"value": "x" * MAX_ENVELOPE_BYTES}))
    with pytest.raises(StateError, match="could not be appended safely"):
        outbox.append(Event("workspace.initialized", {"value": object()}))

    envelope = outbox.append(Event("workspace.initialized", {"safe": True}))
    assert envelope.sequence == 1


def test_consumer_claims_and_acknowledges_events_in_strict_order(tmp_path: Path) -> None:
    outbox = SqliteEventOutbox(tmp_path)
    first = outbox.append(
        Event("workspace.initialized", {"number": 1}),
        event_id=_EVENT_ID,
        occurred_at=_TIMESTAMP,
    )
    second = outbox.append(Event("workspace.initialized", {"number": 2}))
    outbox.register_consumer("webhook.primary", registered_at=_TIMESTAMP)

    first_claim = outbox.claim_next(
        "webhook.primary",
        now=datetime(2026, 8, 4, tzinfo=UTC),
        claim_token=_CLAIM_TOKEN_ONE,
    )
    assert first_claim is not None
    assert first_claim.envelope == first
    assert outbox.claim_next("webhook.primary", now=datetime(2026, 8, 4, tzinfo=UTC)) is None

    outbox.acknowledge(
        "webhook.primary",
        sequence=first.sequence,
        event_id=first.event_id,
        claim_token=first_claim.claim_token,
    )
    second_claim = outbox.claim_next(
        "webhook.primary",
        now=datetime(2026, 8, 4, tzinfo=UTC),
        claim_token=_CLAIM_TOKEN_TWO,
    )
    assert second_claim is not None
    assert second_claim.envelope == second


def test_expired_claim_is_reissued_after_restart_and_stale_worker_is_rejected(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 4, tzinfo=UTC)
    outbox = SqliteEventOutbox(tmp_path)
    event = outbox.append(
        Event("workspace.initialized", {}), event_id=_EVENT_ID, occurred_at=_TIMESTAMP
    )
    outbox.register_consumer("audit", registered_at=_TIMESTAMP)
    old_claim = outbox.claim_next("audit", lease_seconds=10, now=now, claim_token=_CLAIM_TOKEN_ONE)
    assert old_claim is not None

    restarted = SqliteEventOutbox(tmp_path)
    new_claim = restarted.claim_next(
        "audit",
        lease_seconds=10,
        now=now + timedelta(seconds=11),
        claim_token=_CLAIM_TOKEN_TWO,
    )
    assert new_claim is not None
    assert new_claim.envelope == event
    with pytest.raises(StateError, match="stale or invalid"):
        restarted.acknowledge(
            "audit",
            sequence=event.sequence,
            event_id=event.event_id,
            claim_token=old_claim.claim_token,
        )

    assert restarted.claim_next("audit", now=now + timedelta(seconds=12)) is None
    restarted.acknowledge(
        "audit",
        sequence=event.sequence,
        event_id=event.event_id,
        claim_token=new_claim.claim_token,
    )
    assert restarted.claim_next("audit", now=now + timedelta(seconds=12)) is None


def test_parallel_claims_grant_one_lease_only(tmp_path: Path) -> None:
    outbox = SqliteEventOutbox(tmp_path)
    outbox.append(Event("workspace.initialized", {}))
    outbox.register_consumer("parallel")
    now = datetime(2026, 8, 4, tzinfo=UTC)

    with ThreadPoolExecutor(max_workers=8) as executor:
        claims = list(
            executor.map(
                lambda _: SqliteEventOutbox(tmp_path).claim_next("parallel", now=now),
                range(16),
            )
        )

    assert sum(claim is not None for claim in claims) == 1


def test_registration_is_idempotent_but_cannot_move_cursor(tmp_path: Path) -> None:
    outbox = SqliteEventOutbox(tmp_path)
    outbox.register_consumer("export.v2", start_sequence=3, registered_at=_TIMESTAMP)
    outbox.register_consumer("export.v2", start_sequence=3, registered_at=_TIMESTAMP)

    with pytest.raises(StateError, match="another sequence"):
        outbox.register_consumer("export.v2", start_sequence=1)
    with pytest.raises(StateError, match="not registered"):
        outbox.claim_next("missing")
    with pytest.raises(ValueError, match="not canonical"):
        outbox.register_consumer("Export V2")

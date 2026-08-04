"""SQLite durable event outbox tests."""

import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import pytest

from ansiblectl.domain.errors import StateError
from ansiblectl.domain.events import Event
from ansiblectl.infrastructure.event_outbox import MAX_ENVELOPE_BYTES, SqliteEventOutbox

_EVENT_ID = "00000000Z80000000000000000"
_TIMESTAMP = "2026-08-04T00:00:00.000000Z"


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

"""Workspace SQLite outbox for immutable redacted public events."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from ansiblectl.domain.context import new_operation_id
from ansiblectl.domain.durable_events import DurableEventEnvelope
from ansiblectl.domain.errors import StateError
from ansiblectl.domain.events import Event
from ansiblectl.infrastructure.file_locking import locked

SCHEMA_VERSION = 1
MAX_ENVELOPE_BYTES = 256 * 1024
_BUSY_TIMEOUT_MILLISECONDS = 5_000
_SCHEMA = """
CREATE TABLE metadata (schema_version INTEGER NOT NULL CHECK (schema_version = 1));
INSERT INTO metadata(schema_version) VALUES (1);
CREATE TABLE events (
    sequence INTEGER PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    name TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    operation_id TEXT,
    payload_json TEXT NOT NULL
);
CREATE TRIGGER events_immutable
BEFORE UPDATE ON events
BEGIN
    SELECT RAISE(ABORT, 'durable events are immutable');
END;
PRAGMA user_version = 1;
"""


class SqliteEventOutbox:
    """Append and inspect committed event envelopes without delivery side effects."""

    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = workspace_root.resolve()
        self._private_root = self._workspace_root / ".ansiblectl"
        self._directory = self._private_root / "events"
        self._path = self._directory / "outbox.sqlite3"
        self._lock_path = self._directory / "outbox.lock"

    def append(
        self,
        event: Event,
        *,
        operation_id: str | None = None,
        event_id: str | None = None,
        occurred_at: str | None = None,
    ) -> DurableEventEnvelope:
        """Atomically allocate one sequence and persist a safe immutable envelope."""

        safe_payload = event.safe_payload()
        assigned_event_id = event_id or new_operation_id()
        assigned_time = occurred_at or datetime.now(UTC).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        )
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM events"
                ).fetchone()
                assert row is not None
                envelope = DurableEventEnvelope(
                    assigned_event_id,
                    int(row[0]),
                    event.name,
                    assigned_time,
                    operation_id,
                    safe_payload,
                )
                payload_json = _encoded_payload(envelope)
                connection.execute(
                    """
                    INSERT INTO events(
                        sequence, event_id, schema_version, name, occurred_at, operation_id,
                        payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        envelope.sequence,
                        envelope.event_id,
                        envelope.schema_version,
                        envelope.name,
                        envelope.occurred_at,
                        envelope.operation_id,
                        payload_json,
                    ),
                )
                connection.commit()
                return envelope
        except (OSError, sqlite3.Error, TypeError, ValueError) as error:
            raise StateError(
                "Durable event could not be appended safely.",
                hint="Inspect the workspace event outbox and retry.",
            ) from error

    def read_all(self) -> tuple[DurableEventEnvelope, ...]:
        """Read committed envelopes in sequence order for delivery adapters."""

        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    """
                    SELECT event_id, sequence, name, occurred_at, operation_id, payload_json,
                           schema_version
                    FROM events ORDER BY sequence
                    """
                ).fetchall()
            return tuple(_envelope_from_row(row) for row in rows)
        except (OSError, sqlite3.Error, TypeError, ValueError, json.JSONDecodeError) as error:
            raise StateError(
                "Durable event outbox could not be read safely.",
                hint="Inspect the workspace event outbox before retrying.",
            ) from error

    def _connect(self) -> sqlite3.Connection:
        self._prepare_path()
        try:
            with locked(self._lock_path, exclusive=True):
                existed = self._path.exists()
                if not existed:
                    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
                    descriptor = os.open(self._path, flags, 0o600)
                    os.close(descriptor)
                connection = sqlite3.connect(self._path, timeout=_BUSY_TIMEOUT_MILLISECONDS / 1_000)
                self._path.chmod(0o600)
                connection.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MILLISECONDS}")
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute("PRAGMA journal_mode = DELETE")
                connection.execute("PRAGMA synchronous = FULL")
                if existed:
                    version = connection.execute("PRAGMA user_version").fetchone()
                    metadata = connection.execute("SELECT schema_version FROM metadata").fetchone()
                    if version != (SCHEMA_VERSION,) or metadata != (SCHEMA_VERSION,):
                        connection.close()
                        raise StateError("Durable event outbox schema is unsupported.")
                else:
                    connection.executescript(_SCHEMA)
            return connection
        except (OSError, sqlite3.Error):
            if "connection" in locals():
                connection.close()
            raise

    def _prepare_path(self) -> None:
        if not self._workspace_root.is_dir():
            raise StateError("Durable event workspace must be an existing directory.")
        for directory in (self._private_root, self._directory):
            if directory.is_symlink():
                raise StateError("Durable event state must not use symbolic links.")
            directory.mkdir(mode=0o700, exist_ok=True)
            if not directory.is_dir() or not directory.resolve().is_relative_to(
                self._workspace_root
            ):
                raise StateError("Durable event state must remain inside the workspace.")
            directory.chmod(0o700)
        if self._lock_path.is_symlink():
            raise StateError("Durable event outbox lock must not be a symbolic link.")
        if self._path.is_symlink() or (self._path.exists() and not self._path.is_file()):
            raise StateError("Durable event outbox must be a regular non-symlink file.")


def _encoded_payload(envelope: DurableEventEnvelope) -> str:
    encoded = json.dumps(
        envelope.to_payload(),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(encoded.encode("utf-8")) > MAX_ENVELOPE_BYTES:
        raise ValueError("Durable event envelope exceeds its size limit.")
    return json.dumps(
        envelope.to_payload()["payload"],
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _envelope_from_row(row: tuple[object, ...]) -> DurableEventEnvelope:
    event_id, sequence, name, occurred_at, operation_id, payload_json, schema_version = row
    if not isinstance(payload_json, str):
        raise TypeError("Stored durable event payload must be JSON text.")
    payload = json.loads(payload_json)
    return DurableEventEnvelope(
        event_id=event_id,  # type: ignore[arg-type]
        sequence=sequence,  # type: ignore[arg-type]
        name=name,  # type: ignore[arg-type]
        occurred_at=occurred_at,  # type: ignore[arg-type]
        operation_id=operation_id,  # type: ignore[arg-type]
        payload=payload,
        schema_version=schema_version,  # type: ignore[arg-type]
    )


__all__ = ["MAX_ENVELOPE_BYTES", "SCHEMA_VERSION", "SqliteEventOutbox"]

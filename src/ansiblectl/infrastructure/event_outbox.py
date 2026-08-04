"""Workspace SQLite outbox for immutable redacted public events."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ansiblectl.domain.context import new_operation_id
from ansiblectl.domain.durable_events import (
    DurableConsumerStatus,
    DurableEventActionResult,
    DurableEventClaim,
    DurableEventEnvelope,
    DurableEventRetentionResult,
    validate_consumer_id,
)
from ansiblectl.domain.errors import StateError
from ansiblectl.domain.events import Event
from ansiblectl.infrastructure.file_locking import locked

SCHEMA_VERSION = 1
MAX_ENVELOPE_BYTES = 256 * 1024
_BUSY_TIMEOUT_MILLISECONDS = 5_000
_REASON_CODE_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{0,63}")
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
CREATE TABLE consumers (
    consumer_id TEXT PRIMARY KEY,
    next_sequence INTEGER NOT NULL CHECK (next_sequence >= 1),
    registered_at TEXT NOT NULL,
    claim_sequence INTEGER,
    claim_event_id TEXT,
    claim_token TEXT,
    claim_expires_at TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    next_attempt_at TEXT,
    failure_reason TEXT,
    CHECK (
        (claim_sequence IS NULL AND claim_event_id IS NULL AND claim_token IS NULL
         AND claim_expires_at IS NULL)
        OR
        (claim_sequence IS NOT NULL AND claim_event_id IS NOT NULL AND claim_token IS NOT NULL
         AND claim_expires_at IS NOT NULL)
    )
);
CREATE TABLE sequence_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    last_sequence INTEGER NOT NULL CHECK (last_sequence >= 0)
);
INSERT INTO sequence_state(singleton, last_sequence) VALUES (1, 0);
CREATE TRIGGER events_immutable
BEFORE UPDATE ON events
BEGIN
    SELECT RAISE(ABORT, 'durable events are immutable');
END;
PRAGMA user_version = 1;
"""
_CONSUMER_SCHEMA = """
CREATE TABLE IF NOT EXISTS consumers (
    consumer_id TEXT PRIMARY KEY,
    next_sequence INTEGER NOT NULL CHECK (next_sequence >= 1),
    registered_at TEXT NOT NULL,
    claim_sequence INTEGER,
    claim_event_id TEXT,
    claim_token TEXT,
    claim_expires_at TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    next_attempt_at TEXT,
    failure_reason TEXT,
    CHECK (
        (claim_sequence IS NULL AND claim_event_id IS NULL AND claim_token IS NULL
         AND claim_expires_at IS NULL)
        OR
        (claim_sequence IS NOT NULL AND claim_event_id IS NOT NULL AND claim_token IS NOT NULL
         AND claim_expires_at IS NOT NULL)
    )
);
"""
_SEQUENCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS sequence_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    last_sequence INTEGER NOT NULL CHECK (last_sequence >= 0)
);
INSERT OR IGNORE INTO sequence_state(singleton, last_sequence)
SELECT 1, COALESCE(MAX(sequence), 0) FROM events;
"""


class SqliteEventOutbox:
    """Append and inspect committed event envelopes without delivery side effects."""

    def __init__(
        self,
        workspace_root: Path,
        *,
        checkpoint: Callable[[str], None] | None = None,
    ) -> None:
        self._workspace_root = workspace_root.resolve()
        self._private_root = self._workspace_root / ".ansiblectl"
        self._directory = self._private_root / "events"
        self._path = self._directory / "outbox.sqlite3"
        self._lock_path = self._directory / "outbox.lock"
        self._checkpoint = checkpoint or (lambda _name: None)

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
                envelope = DurableEventEnvelope(
                    assigned_event_id,
                    _allocate_sequence(connection),
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
                self._checkpoint("append.inserted")
                connection.commit()
                self._checkpoint("append.committed")
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

    def register_consumer(
        self,
        consumer_id: str,
        *,
        start_sequence: int = 1,
        registered_at: str | None = None,
    ) -> bool:
        """Idempotently establish a consumer's first desired sequence."""

        validate_consumer_id(consumer_id)
        _validate_sequence(start_sequence)
        assigned_time = registered_at or _canonical_time(datetime.now(UTC))
        _parse_time(assigned_time)
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT next_sequence FROM consumers WHERE consumer_id = ?",
                    (consumer_id,),
                ).fetchone()
                if row is None:
                    connection.execute(
                        "INSERT INTO consumers(consumer_id, next_sequence, registered_at) "
                        "VALUES (?, ?, ?)",
                        (consumer_id, start_sequence, assigned_time),
                    )
                    applied = True
                elif row != (start_sequence,):
                    raise StateError(
                        "Durable event consumer is already registered at another sequence."
                    )
                else:
                    applied = False
                connection.commit()
                return applied
        except (OSError, sqlite3.Error) as error:
            raise StateError("Durable event consumer could not be registered safely.") from error

    def claim_next(
        self,
        consumer_id: str,
        *,
        lease_seconds: int = 30,
        now: datetime | None = None,
        claim_token: str | None = None,
    ) -> DurableEventClaim | None:
        """Lease only the consumer's exact next sequence, if it is available."""

        validate_consumer_id(consumer_id)
        if (
            not isinstance(lease_seconds, int)
            or isinstance(lease_seconds, bool)
            or lease_seconds < 1
        ):
            raise ValueError("Durable event lease must be a positive integer number of seconds.")
        current = now or datetime.now(UTC)
        current_text = _canonical_time(current)
        assigned_token = claim_token or new_operation_id()
        expires_at = _canonical_time(current + timedelta(seconds=lease_seconds))
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                consumer = connection.execute(
                    """
                    SELECT next_sequence, claim_expires_at, next_attempt_at, failure_reason
                    FROM consumers WHERE consumer_id = ?
                    """,
                    (consumer_id,),
                ).fetchone()
                if consumer is None:
                    raise StateError("Durable event consumer is not registered.")
                next_sequence, active_expiry, next_attempt_at, failure_reason = consumer
                if isinstance(active_expiry, str) and active_expiry > current_text:
                    connection.rollback()
                    return None
                if failure_reason is not None and next_attempt_at is None:
                    connection.rollback()
                    return None
                if isinstance(next_attempt_at, str) and next_attempt_at > current_text:
                    connection.rollback()
                    return None
                row = connection.execute(
                    """
                    SELECT event_id, sequence, name, occurred_at, operation_id, payload_json,
                           schema_version
                    FROM events WHERE sequence = ?
                    """,
                    (next_sequence,),
                ).fetchone()
                if row is None:
                    connection.execute(
                        """
                        UPDATE consumers SET claim_sequence = NULL, claim_event_id = NULL,
                                             claim_token = NULL, claim_expires_at = NULL
                        WHERE consumer_id = ?
                        """,
                        (consumer_id,),
                    )
                    connection.commit()
                    return None
                envelope = _envelope_from_row(row)
                claim = DurableEventClaim(consumer_id, assigned_token, expires_at, envelope)
                connection.execute(
                    """
                    UPDATE consumers
                    SET claim_sequence = ?, claim_event_id = ?, claim_token = ?,
                        claim_expires_at = ?
                    WHERE consumer_id = ? AND next_sequence = ?
                    """,
                    (
                        envelope.sequence,
                        envelope.event_id,
                        claim.claim_token,
                        claim.lease_expires_at,
                        consumer_id,
                        envelope.sequence,
                    ),
                )
                connection.commit()
                return claim
        except (OSError, sqlite3.Error, TypeError, ValueError, json.JSONDecodeError) as error:
            raise StateError("Durable event could not be claimed safely.") from error

    def acknowledge(
        self,
        consumer_id: str,
        *,
        sequence: int,
        event_id: str,
        claim_token: str,
    ) -> None:
        """Advance a consumer only when every claim identity field still matches."""

        validate_consumer_id(consumer_id)
        _validate_sequence(sequence)
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """
                    UPDATE consumers
                    SET next_sequence = next_sequence + 1,
                        claim_sequence = NULL, claim_event_id = NULL,
                        claim_token = NULL, claim_expires_at = NULL,
                        attempt_count = 0, next_attempt_at = NULL, failure_reason = NULL
                    WHERE consumer_id = ? AND next_sequence = ? AND claim_sequence = ?
                      AND claim_event_id = ? AND claim_token = ?
                    """,
                    (consumer_id, sequence, sequence, event_id, claim_token),
                )
                if cursor.rowcount != 1:
                    raise StateError("Durable event acknowledgement is stale or invalid.")
                connection.commit()
        except (OSError, sqlite3.Error) as error:
            raise StateError("Durable event could not be acknowledged safely.") from error

    def record_failure(
        self,
        consumer_id: str,
        *,
        sequence: int,
        event_id: str,
        claim_token: str,
        reason_code: str,
        retry_delays: tuple[int, ...],
        max_attempts: int,
        now: datetime | None = None,
    ) -> None:
        """Persist one redacted delivery failure and its deterministic retry time."""

        validate_consumer_id(consumer_id)
        _validate_sequence(sequence)
        _validate_retry_policy(reason_code, retry_delays, max_attempts)
        current = now or datetime.now(UTC)
        _canonical_time(current)
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    """
                    SELECT attempt_count FROM consumers
                    WHERE consumer_id = ? AND next_sequence = ? AND claim_sequence = ?
                      AND claim_event_id = ? AND claim_token = ?
                    """,
                    (consumer_id, sequence, sequence, event_id, claim_token),
                ).fetchone()
                if row is None:
                    raise StateError("Durable event failure update is stale or invalid.")
                attempt_count = int(row[0]) + 1
                next_attempt_at = None
                if attempt_count < max_attempts:
                    delay = retry_delays[min(attempt_count - 1, len(retry_delays) - 1)]
                    next_attempt_at = _canonical_time(current + timedelta(seconds=delay))
                cursor = connection.execute(
                    """
                    UPDATE consumers
                    SET claim_sequence = NULL, claim_event_id = NULL,
                        claim_token = NULL, claim_expires_at = NULL,
                        attempt_count = ?, next_attempt_at = ?, failure_reason = ?
                    WHERE consumer_id = ? AND next_sequence = ? AND claim_sequence = ?
                      AND claim_event_id = ? AND claim_token = ?
                    """,
                    (
                        attempt_count,
                        next_attempt_at,
                        reason_code,
                        consumer_id,
                        sequence,
                        sequence,
                        event_id,
                        claim_token,
                    ),
                )
                if cursor.rowcount != 1:
                    raise StateError("Durable event failure update is stale or invalid.")
                connection.commit()
        except (OSError, sqlite3.Error) as error:
            raise StateError("Durable event failure could not be recorded safely.") from error

    def retry(
        self,
        consumer_id: str,
        *,
        sequence: int,
        event_id: str,
    ) -> None:
        """Reset scheduling for one exact blocked consumer event."""

        validate_consumer_id(consumer_id)
        _validate_sequence(sequence)
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """
                    UPDATE consumers
                    SET claim_sequence = NULL, claim_event_id = NULL,
                        claim_token = NULL, claim_expires_at = NULL,
                        attempt_count = 0, next_attempt_at = NULL, failure_reason = NULL
                    WHERE consumer_id = ? AND next_sequence = ? AND failure_reason IS NOT NULL
                      AND claim_token IS NULL
                      AND EXISTS(
                          SELECT 1 FROM events WHERE sequence = ? AND event_id = ?
                      )
                    """,
                    (consumer_id, sequence, sequence, event_id),
                )
                if cursor.rowcount != 1:
                    raise StateError("Durable event retry target is not blocked or does not match.")
                connection.commit()
        except (OSError, sqlite3.Error) as error:
            raise StateError("Durable event retry could not be applied safely.") from error

    def abandon(
        self,
        consumer_id: str,
        *,
        sequence: int,
        event_id: str,
        apply: bool = False,
    ) -> DurableEventActionResult:
        """Preview or explicitly abandon one exact blocked event and audit the action."""

        validate_consumer_id(consumer_id)
        _validate_sequence(sequence)
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    """
                    SELECT 1 FROM consumers
                    WHERE consumer_id = ? AND next_sequence = ? AND failure_reason IS NOT NULL
                      AND claim_token IS NULL
                      AND EXISTS(
                          SELECT 1 FROM events WHERE sequence = ? AND event_id = ?
                      )
                    """,
                    (consumer_id, sequence, sequence, event_id),
                ).fetchone()
                if row is None:
                    raise StateError(
                        "Durable event abandon target is not blocked or does not match."
                    )
                result = DurableEventActionResult(consumer_id, sequence, event_id, apply)
                if not apply:
                    connection.rollback()
                    return result
                connection.execute(
                    """
                    UPDATE consumers
                    SET next_sequence = next_sequence + 1,
                        claim_sequence = NULL, claim_event_id = NULL,
                        claim_token = NULL, claim_expires_at = NULL,
                        attempt_count = 0, next_attempt_at = NULL, failure_reason = NULL
                    WHERE consumer_id = ? AND next_sequence = ?
                    """,
                    (consumer_id, sequence),
                )
                self._append_in_transaction(
                    connection,
                    Event(
                        "event.delivery.abandoned",
                        {"consumer_id": consumer_id, "sequence": sequence, "event_id": event_id},
                    ),
                )
                connection.commit()
                return result
        except (OSError, sqlite3.Error, TypeError, ValueError) as error:
            raise StateError("Durable event abandon could not be applied safely.") from error

    def inspect_consumers(
        self, *, now: datetime | None = None
    ) -> tuple[DurableConsumerStatus, ...]:
        """Return payload-free delivery summaries without mutating scheduling."""

        current_text = _canonical_time(now or datetime.now(UTC))
        try:
            with closing(self._connect()) as connection:
                event_count = int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])
                rows = connection.execute(
                    """
                    SELECT consumer_id, next_sequence, attempt_count, next_attempt_at,
                           failure_reason, claim_expires_at,
                           (SELECT COUNT(*) FROM events
                            WHERE sequence >= consumers.next_sequence),
                           (SELECT MIN(sequence) FROM events
                            WHERE sequence >= consumers.next_sequence)
                    FROM consumers ORDER BY consumer_id
                    """
                ).fetchall()
            return tuple(
                _consumer_status(row, event_count=event_count, now=current_text) for row in rows
            )
        except (OSError, sqlite3.Error, TypeError, ValueError) as error:
            raise StateError("Durable event consumers could not be inspected safely.") from error

    def retain(self, *, apply: bool = False) -> DurableEventRetentionResult:
        """Preview or remove only the prefix completed by every registered consumer."""

        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT MIN(next_sequence) - 1, COUNT(*) FROM consumers"
                ).fetchone()
                assert row is not None
                through_sequence = row[0] if int(row[1]) > 0 else None
                event_count = 0
                if isinstance(through_sequence, int) and through_sequence >= 1:
                    event_count = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM events WHERE sequence <= ?",
                            (through_sequence,),
                        ).fetchone()[0]
                    )
                result = DurableEventRetentionResult(
                    through_sequence if event_count else None, event_count, apply
                )
                if apply and event_count:
                    connection.execute(
                        "DELETE FROM events WHERE sequence <= ?", (through_sequence,)
                    )
                    connection.commit()
                else:
                    connection.rollback()
                return result
        except (OSError, sqlite3.Error) as error:
            raise StateError("Durable event retention could not be applied safely.") from error

    def _append_in_transaction(
        self, connection: sqlite3.Connection, event: Event
    ) -> DurableEventEnvelope:
        envelope = DurableEventEnvelope(
            new_operation_id(),
            _allocate_sequence(connection),
            event.name,
            _canonical_time(datetime.now(UTC)),
            None,
            event.safe_payload(),
        )
        connection.execute(
            """
            INSERT INTO events(
                sequence, event_id, schema_version, name, occurred_at, operation_id, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                envelope.sequence,
                envelope.event_id,
                envelope.schema_version,
                envelope.name,
                envelope.occurred_at,
                envelope.operation_id,
                _encoded_payload(envelope),
            ),
        )
        return envelope

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
                connection.executescript(_CONSUMER_SCHEMA)
                connection.executescript(_SEQUENCE_SCHEMA)
                columns = {
                    str(row[1]) for row in connection.execute("PRAGMA table_info(consumers)")
                }
                for name, definition in (
                    ("attempt_count", "INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0)"),
                    ("next_attempt_at", "TEXT"),
                    ("failure_reason", "TEXT"),
                ):
                    if name not in columns:
                        connection.execute(f"ALTER TABLE consumers ADD COLUMN {name} {definition}")
                integrity = connection.execute("PRAGMA quick_check").fetchone()
                if integrity != ("ok",):
                    connection.close()
                    raise StateError("Durable event outbox is corrupt.")
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


def _canonical_time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("Durable event time must be timezone-aware UTC.")
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except (TypeError, ValueError) as error:
        raise ValueError("Durable event time must be canonical UTC with microseconds.") from error
    if _canonical_time(parsed) != value:
        raise ValueError("Durable event time must be canonical UTC with microseconds.")
    return parsed


def _validate_sequence(sequence: object) -> int:
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise ValueError("Durable event sequence must be a positive integer.")
    return sequence


def _allocate_sequence(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "UPDATE sequence_state SET last_sequence = last_sequence + 1 "
        "WHERE singleton = 1 RETURNING last_sequence"
    ).fetchone()
    if row is None:
        raise sqlite3.IntegrityError("durable event sequence state is missing")
    return int(row[0])


def _validate_retry_policy(reason_code: object, retry_delays: object, max_attempts: object) -> None:
    if not isinstance(reason_code, str) or not _REASON_CODE_PATTERN.fullmatch(reason_code):
        raise ValueError("Durable event failure reason code is not canonical.")
    if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
        raise ValueError("Durable event maximum attempts must be a positive integer.")
    if (
        not isinstance(retry_delays, tuple)
        or not retry_delays
        or any(
            not isinstance(delay, int) or isinstance(delay, bool) or delay < 1
            for delay in retry_delays
        )
    ):
        raise ValueError("Durable event retry delays must be positive integer seconds.")


def _consumer_status(
    row: tuple[object, ...], *, event_count: int, now: str
) -> DurableConsumerStatus:
    (
        consumer_id,
        next_sequence,
        attempt_count,
        next_attempt_at,
        failure_reason,
        claim_expires_at,
        pending_count,
        lowest_pending_sequence,
    ) = row
    if (
        not isinstance(consumer_id, str)
        or not isinstance(next_sequence, int)
        or not isinstance(attempt_count, int)
        or not isinstance(pending_count, int)
        or (lowest_pending_sequence is not None and not isinstance(lowest_pending_sequence, int))
    ):
        raise TypeError("Stored durable event consumer state is invalid.")
    state = "idle"
    if pending_count:
        state = "pending"
        if isinstance(claim_expires_at, str) and claim_expires_at > now:
            state = "claimed"
        elif failure_reason is not None and next_attempt_at is None:
            state = "exhausted"
        elif isinstance(next_attempt_at, str) and next_attempt_at > now:
            state = "delayed"
    return DurableConsumerStatus(
        consumer_id,
        event_count,
        pending_count,
        lowest_pending_sequence,
        attempt_count,
        next_attempt_at if isinstance(next_attempt_at, str) else None,
        state,
    )


__all__ = ["MAX_ENVELOPE_BYTES", "SCHEMA_VERSION", "SqliteEventOutbox"]

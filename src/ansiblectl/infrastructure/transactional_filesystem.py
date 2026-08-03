"""Durable, auditable filesystem transactions scoped to one trusted root."""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import tempfile
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from ansiblectl.domain.errors import FilesystemRecoveryError, FilesystemTransactionError
from ansiblectl.domain.logging import LogEvent, LogSink, emit
from ansiblectl.infrastructure.file_locking import locked

_CONTROL: Final = ".ansiblectl/transactions"


@dataclass(frozen=True)
class RecoveryResult:
    """Summary of one automatic recovery pass."""

    rolled_back: tuple[str, ...]


class TransactionalFilesystem:
    """Create isolated write sets and recover interrupted commits."""

    def __init__(self, root: Path, *, audit_sink: LogSink | None = None) -> None:
        self.root = root.resolve()
        self.audit_sink = audit_sink
        self.control = self.root / _CONTROL

    def begin(self, *, correlation_id: str | None = None) -> FilesystemTransaction:
        """Create a durable staging area for a new transaction."""

        self.control.mkdir(parents=True, exist_ok=True, mode=0o700)
        transaction_id = uuid.uuid4().hex
        directory = self.control / transaction_id
        directory.mkdir(mode=0o700)
        transaction = FilesystemTransaction(
            filesystem=self,
            transaction_id=transaction_id,
            directory=directory,
            correlation_id=correlation_id,
            active_descriptor=_acquire_owner_lock(directory, blocking=True),
        )
        transaction._persist("staging")
        transaction._audit("filesystem.transaction.started")
        return transaction

    def recover(self) -> RecoveryResult:
        """Roll back every interrupted transaction; committed journals are cleaned up."""

        if not self.control.exists():
            return RecoveryResult(())
        recovered: list[str] = []
        with locked(self.control / ".lock", exclusive=True):
            for directory in sorted(self.control.iterdir()):
                if not directory.is_dir():
                    continue
                transaction = FilesystemTransaction._load_inactive(self, directory)
                if transaction is None:
                    continue
                if transaction.state == "committed":
                    transaction._cleanup()
                    continue
                try:
                    transaction.rollback()
                except FilesystemTransactionError as error:
                    raise FilesystemRecoveryError(
                        "Automatic filesystem recovery failed.",
                        hint="Inspect the retained transaction journal before retrying.",
                        context={"transaction_id": transaction.transaction_id},
                        cause=error,
                    ) from error
                recovered.append(transaction.transaction_id)
        return RecoveryResult(tuple(recovered))

    def pending(self) -> tuple[str, ...]:
        """Return durable transaction identifiers requiring rollback or cleanup."""

        if not self.control.exists():
            return ()
        with locked(self.control / ".lock", exclusive=False):
            identifiers: list[str] = []
            for directory in sorted(self.control.iterdir()):
                if not directory.is_dir():
                    continue
                transaction = FilesystemTransaction._load_inactive(self, directory)
                if transaction is None:
                    continue
                identifiers.append(directory.name)
                transaction._release_active()
            return tuple(identifiers)


class FilesystemTransaction:
    """A staged set of writes and deletions committed as one recoverable unit."""

    def __init__(
        self,
        *,
        filesystem: TransactionalFilesystem,
        transaction_id: str,
        directory: Path,
        correlation_id: str | None,
        active_descriptor: int | None = None,
    ) -> None:
        self.filesystem = filesystem
        self.transaction_id = transaction_id
        self.directory = directory
        self.correlation_id = correlation_id
        self._active_descriptor = active_descriptor
        self.state = "staging"
        self.operations: list[dict[str, Any]] = []

    def stage_write(self, path: Path, content: bytes, *, mode: int = 0o600) -> None:
        """Stage bytes for atomic replacement at *path*."""

        self._require_staging()
        target = self._target(path)
        if not isinstance(content, bytes):
            raise TypeError("Transactional write content must be bytes.")
        staged = self.directory / f"stage-{len(self.operations)}"
        descriptor = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        self.operations.append({"kind": "write", "target": str(target), "staged": str(staged)})
        self._persist("staging")

    def stage_delete(self, path: Path) -> None:
        """Stage removal of a file; missing targets remain a safe no-op."""

        self._require_staging()
        target = self._target(path)
        self.operations.append({"kind": "delete", "target": str(target)})
        self._persist("staging")

    def commit(self) -> None:
        """Apply staged operations atomically per path, retaining rollback data until durable."""

        self._require_staging()
        with locked(self.filesystem.control / ".lock", exclusive=True):
            try:
                self._persist("committing")
                for index, operation in enumerate(self.operations):
                    self._apply(index, operation)
                    self._persist("committing")
                self._persist("committed")
                _fsync_directory(self.filesystem.root)
            except OSError as error:
                try:
                    self.rollback()
                except FilesystemTransactionError as rollback_error:
                    raise FilesystemRecoveryError(
                        "Filesystem commit and automatic rollback both failed.",
                        context={"transaction_id": self.transaction_id},
                        cause=rollback_error,
                    ) from error
                raise FilesystemTransactionError(
                    "Filesystem transaction could not be committed and was rolled back.",
                    context={"transaction_id": self.transaction_id},
                    cause=error,
                ) from error
            self._audit("filesystem.transaction.committed", operation_count=len(self.operations))
            self._cleanup()

    def rollback(self) -> None:
        """Restore all applied targets in reverse order; safe to retry after interruption."""

        try:
            for operation in reversed(self.operations):
                if not operation.get("applied"):
                    continue
                target = Path(operation["target"])
                self._validate_target_stable(target)
                backup = Path(operation["backup"]) if operation.get("backup") else None
                if backup is not None and backup.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    _restore_backup(backup, target)
                else:
                    target.unlink(missing_ok=True)
                operation["applied"] = False
                self._persist("rolling_back")
            self._persist("rolled_back")
        except OSError as error:
            raise FilesystemTransactionError(
                "Filesystem transaction rollback failed.",
                hint="Retain the transaction journal and run recovery again.",
                context={"transaction_id": self.transaction_id},
                cause=error,
            ) from error
        self._audit("filesystem.transaction.rolled_back", operation_count=len(self.operations))
        self._cleanup()

    def _apply(self, index: int, operation: dict[str, Any]) -> None:
        target = Path(operation["target"])
        self._validate_target_stable(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.parent.resolve() != target.parent:
            raise OSError(f"Transaction target parent is not stable: {target.parent}")
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise OSError(f"Transaction target is not a regular file: {target}")
        if target.exists():
            backup = self.directory / f"backup-{index}"
            shutil.copy2(target, backup)
            _fsync_file(backup)
            operation["backup"] = str(backup)
            self._persist("committing")
        operation["applied"] = True
        self._persist("committing")
        if operation["kind"] == "write":
            os.replace(operation["staged"], target)
        else:
            target.unlink(missing_ok=True)
        _fsync_directory(target.parent)

    def _validate_target_stable(self, target: Path) -> None:
        resolved_target = target.resolve(strict=False)
        if resolved_target != target or not resolved_target.is_relative_to(self.filesystem.root):
            raise OSError(f"Transaction target changed after staging: {target}")

    def _target(self, path: Path) -> Path:
        target = path if path.is_absolute() else self.filesystem.root / path
        target = target.resolve(strict=False)
        try:
            target.relative_to(self.filesystem.root)
        except ValueError as error:
            raise FilesystemTransactionError(
                "Filesystem transaction target escapes its configured root.",
                context={"path": str(path)},
            ) from error
        if target == self.filesystem.root or self.filesystem.control in target.parents:
            raise FilesystemTransactionError("Filesystem transaction target is reserved.")
        if any(operation["target"] == str(target) for operation in self.operations):
            raise FilesystemTransactionError(
                "Filesystem transaction target was staged more than once.",
                context={"path": str(path)},
            )
        return target

    def _require_staging(self) -> None:
        if self.state != "staging":
            raise FilesystemTransactionError(
                "Filesystem transaction is no longer open for changes.",
                context={"transaction_id": self.transaction_id, "state": self.state},
            )

    def _persist(self, state: str) -> None:
        self.state = state
        journal = self.directory / "journal.json"
        payload = {
            "schema_version": 1,
            "transaction_id": self.transaction_id,
            "state": state,
            "correlation_id": self.correlation_id,
            "operations": self.operations,
        }
        descriptor, name = tempfile.mkstemp(prefix=".journal-", dir=self.directory)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, journal)
            _fsync_directory(self.directory)
        finally:
            temporary.unlink(missing_ok=True)

    def _audit(self, name: str, **fields: object) -> None:
        if self.filesystem.audit_sink is not None:
            emit(
                self.filesystem.audit_sink,
                LogEvent(
                    level="info",
                    name=name,
                    correlation_id=self.correlation_id,
                    fields={"transaction_id": self.transaction_id, **fields},
                ),
            )

    def _cleanup(self) -> None:
        shutil.rmtree(self.directory, ignore_errors=False)
        _fsync_directory(self.filesystem.control)
        self._release_active()

    @classmethod
    def _load(cls, filesystem: TransactionalFilesystem, directory: Path) -> FilesystemTransaction:
        try:
            data: Mapping[str, Any] = json.loads(
                (directory / "journal.json").read_text(encoding="utf-8")
            )
            if data.get("schema_version") != 1 or data.get("transaction_id") != directory.name:
                raise ValueError("unsupported transaction journal")
            transaction = cls(
                filesystem=filesystem,
                transaction_id=directory.name,
                directory=directory,
                correlation_id=data.get("correlation_id"),
            )
            transaction.state = str(data["state"])
            transaction.operations = list(data["operations"])
            return transaction
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            raise FilesystemRecoveryError(
                "Filesystem transaction journal is unreadable.",
                context={"transaction_id": directory.name},
                cause=error,
            ) from error

    @classmethod
    def _load_inactive(
        cls, filesystem: TransactionalFilesystem, directory: Path
    ) -> FilesystemTransaction | None:
        descriptor = _acquire_owner_lock(directory, blocking=False)
        if descriptor is None:
            return None
        try:
            transaction = cls._load(filesystem, directory)
        except BaseException:
            os.close(descriptor)
            raise
        transaction._active_descriptor = descriptor
        return transaction

    def _release_active(self) -> None:
        if self._active_descriptor is not None:
            fcntl.flock(self._active_descriptor, fcntl.LOCK_UN)
            os.close(self._active_descriptor)
            self._active_descriptor = None


def _fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _restore_backup(backup: Path, target: Path) -> None:
    descriptor, name = tempfile.mkstemp(prefix=".rollback-", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as destination, backup.open("rb") as source:
            shutil.copyfileobj(source, destination)
            destination.flush()
            os.fsync(destination.fileno())
        shutil.copymode(backup, temporary)
        os.replace(temporary, target)
        _fsync_directory(target.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _acquire_owner_lock(directory: Path, *, blocking: bool) -> int | None:
    descriptor = os.open(directory / "active.lock", os.O_RDWR | os.O_CREAT, 0o600)
    flags = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
    try:
        fcntl.flock(descriptor, flags)
    except BlockingIOError:
        os.close(descriptor)
        return None
    return descriptor


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

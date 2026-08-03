"""Atomic JSON state scoped to an Ansiblectl workspace."""

from __future__ import annotations

import json
from pathlib import Path

from ansiblectl.domain.errors import FilesystemTransactionError
from ansiblectl.domain.errors import StateError as StateError
from ansiblectl.domain.state import CacheEntry as CacheEntry
from ansiblectl.domain.state import StateInvalidationResult
from ansiblectl.infrastructure.file_locking import locked
from ansiblectl.infrastructure.transactional_filesystem import TransactionalFilesystem

SCHEMA_VERSION = 1


class WorkspaceStateStore:
    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = workspace_root.resolve()
        self._path = self._workspace_root / ".ansiblectl/state.json"
        self._lock_path = self._workspace_root / ".ansiblectl/state.lock"

    def read(self) -> dict[str, CacheEntry]:
        self._validate_boundary()
        if not self._path.is_file():
            return {}
        try:
            with locked(self._lock_path, exclusive=False):
                return self._read_entries()
        except (OSError, FilesystemTransactionError) as error:
            raise StateError(
                "State could not be read safely. Check workspace permissions."
            ) from error

    def _read_entries(self) -> dict[str, CacheEntry]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise StateError(
                "State is corrupt. Remove .ansiblectl/state.json and retry."
            ) from error
        if (
            not isinstance(data, dict)
            or data.get("schema_version") != SCHEMA_VERSION
            or not isinstance(data.get("entries"), dict)
        ):
            raise StateError(
                "State schema is unsupported. Remove .ansiblectl/state.json to reset it."
            )
        try:
            entries: dict[str, CacheEntry] = {}
            for name, entry in data["entries"].items():
                if not isinstance(name, str) or not name.strip():
                    raise TypeError("Cache entry names must be non-empty strings.")
                entries[name] = CacheEntry(**entry)
            return entries
        except (TypeError, StateError) as error:
            raise StateError(
                "State is corrupt. Remove .ansiblectl/state.json and retry."
            ) from error

    def write(self, entries: dict[str, CacheEntry]) -> None:
        self._prepare_parent()
        try:
            with locked(self._lock_path, exclusive=True):
                self._write_entries(entries)
        except (OSError, FilesystemTransactionError) as error:
            raise StateError(
                "State could not be written safely. Check workspace permissions."
            ) from error

    def invalidate(self, name: str, *, apply: bool) -> StateInvalidationResult:
        if not name.strip():
            raise StateError("Cache entry name must be non-empty.")
        self._prepare_parent()
        try:
            with locked(self._lock_path, exclusive=True):
                entries = self._read_entries() if self._path.is_file() else {}
                existed = name in entries
                remaining_count = len(entries) - int(existed)
                if apply and existed:
                    del entries[name]
                    self._write_entries(entries)
        except OSError as error:
            raise StateError(
                "State invalidation failed safely. Check workspace permissions."
            ) from error
        return StateInvalidationResult(name, existed, apply, remaining_count)

    def _write_entries(self, entries: dict[str, CacheEntry]) -> None:
        data = {
            "schema_version": SCHEMA_VERSION,
            "entries": {
                name: {
                    "source_identity": entry.source_identity,
                    "invalidation_condition": entry.invalidation_condition,
                    "value": entry.value,
                }
                for name, entry in entries.items()
            },
        }
        content = (json.dumps(data, sort_keys=True) + "\n").encode()
        transaction = TransactionalFilesystem(self._workspace_root).begin()
        transaction.stage_write(self._path, content)
        transaction.commit()

    def _prepare_parent(self) -> None:
        self._validate_boundary()
        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._validate_boundary()
        self._path.parent.chmod(0o700)

    def _validate_boundary(self) -> None:
        parent = self._path.parent
        if parent.exists() and not parent.resolve().is_relative_to(self._workspace_root):
            raise StateError("State path must remain inside the selected workspace.")
        if self._path.is_symlink():
            raise StateError("State file must not be a symbolic link. Remove it and retry.")
        if self._lock_path.is_symlink():
            raise StateError("State lock must not be a symbolic link. Remove it and retry.")

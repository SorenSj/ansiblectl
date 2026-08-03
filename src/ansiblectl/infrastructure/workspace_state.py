"""Atomic JSON state scoped to an Ansiblectl workspace."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from ansiblectl.domain.errors import StateError as StateError
from ansiblectl.domain.state import CacheEntry as CacheEntry

SCHEMA_VERSION = 1


class WorkspaceStateStore:
    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = workspace_root.resolve()
        self._path = self._workspace_root / ".ansiblectl/state.json"

    def read(self) -> dict[str, CacheEntry]:
        self._validate_boundary()
        if not self._path.is_file():
            return {}
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
        self._validate_boundary()
        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._validate_boundary()
        self._path.parent.chmod(0o700)
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
        descriptor, name = tempfile.mkstemp(prefix=".state-", dir=self._path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(data, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self._path)
        finally:
            temporary.unlink(missing_ok=True)

    def _validate_boundary(self) -> None:
        parent = self._path.parent
        if parent.exists() and not parent.resolve().is_relative_to(self._workspace_root):
            raise StateError("State path must remain inside the selected workspace.")
        if self._path.is_symlink():
            raise StateError("State file must not be a symbolic link. Remove it and retry.")

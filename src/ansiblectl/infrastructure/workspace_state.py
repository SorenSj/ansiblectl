"""Atomic JSON state scoped to an Ansiblectl workspace."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = 1


class StateError(Exception):
    """Safe persistent-state error with a reset path."""


@dataclass(frozen=True)
class CacheEntry:
    source_identity: str
    invalidation_condition: str
    value: dict[str, object]


class WorkspaceStateStore:
    def __init__(self, workspace_root: Path) -> None:
        self._path = workspace_root / ".ansiblectl/state.json"

    def read(self) -> dict[str, CacheEntry]:
        if not self._path.is_file():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise StateError(
                "State is corrupt. Remove .ansiblectl/state.json and retry."
            ) from error
        if data.get("schema_version") != SCHEMA_VERSION or not isinstance(
            data.get("entries"), dict
        ):
            raise StateError(
                "State schema is unsupported. Remove .ansiblectl/state.json to reset it."
            )
        return {name: CacheEntry(**entry) for name, entry in data["entries"].items()}

    def write(self, entries: dict[str, CacheEntry]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
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

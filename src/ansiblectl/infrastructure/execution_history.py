"""Read safe execution records from the private structured event log."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ansiblectl.domain.errors import ExecutionError
from ansiblectl.domain.execution import (
    ExecutionMode,
    ExecutionRecord,
    ExecutionRetentionResult,
    ExecutionStatus,
    ExecutionTargeting,
)
from ansiblectl.infrastructure.file_locking import locked


@dataclass(frozen=True)
class JsonLinesExecutionHistory:
    workspace_root: Path

    @property
    def path(self) -> Path:
        return self.workspace_root / ".ansiblectl" / "logs" / "events.jsonl"

    def list(self) -> tuple[ExecutionRecord, ...]:
        """Return completed executions newest first."""

        path = self._validated_path()
        if not path.exists():
            return ()
        try:
            with locked(path.parent / "events.lock", exclusive=False):
                entries = _read_entries(path)
            records = [_parse_record(entry) for entry in entries]
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise ExecutionError(
                "Execution history is unreadable. Repair or remove "
                ".ansiblectl/logs/events.jsonl and retry."
            ) from error
        return tuple(record for record in reversed(records) if record is not None)

    def get(self, execution_id: str) -> ExecutionRecord:
        """Return one execution by its exact identifier."""

        for record in self.list():
            if record.execution_id == execution_id:
                return record
        raise ExecutionError(f"Execution '{execution_id}' was not found in this workspace.")

    def prune(self, keep: int) -> ExecutionRetentionResult:
        """Atomically retain newest records and remove only derived output directories."""

        if keep < 0:
            raise ExecutionError("Execution retention count must be zero or greater.")
        path = self._validated_path()
        if not path.exists():
            return ExecutionRetentionResult(0, (), True)
        try:
            with locked(path.parent / "events.lock", exclusive=True):
                entries = _read_entries(path)
                executions = [
                    (index, record)
                    for index, entry in enumerate(entries)
                    if (record := _parse_record(entry)) is not None
                ]
                remove_count = max(0, len(executions) - keep)
                removed = executions[:remove_count]
                removed_indices = {index for index, _ in removed}
                _atomic_write(
                    path,
                    [entry for index, entry in enumerate(entries) if index not in removed_indices],
                )
                for _, record in removed:
                    self._remove_output_directory(record.execution_id)
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise ExecutionError(
                "Execution retention failed safely. Inspect workspace permissions and history."
            ) from error
        return ExecutionRetentionResult(
            len(executions) - len(removed),
            tuple(record.execution_id for _, record in reversed(removed)),
            True,
        )

    def _remove_output_directory(self, execution_id: str) -> None:
        key = hashlib.sha256(execution_id.encode("utf-8")).hexdigest()
        directory = self.workspace_root.resolve() / ".ansiblectl" / "runs" / key
        if directory.is_symlink():
            directory.unlink()
            return
        if not directory.is_dir():
            return
        for filename in ("stdout.log", "stderr.log"):
            (directory / filename).unlink(missing_ok=True)
        with suppress(OSError):
            directory.rmdir()

    def _validated_path(self) -> Path:
        root = self.workspace_root.resolve()
        path = self.path.resolve()
        if not path.is_relative_to(root):
            raise ExecutionError("Execution history must remain inside the selected workspace.")
        return path


def _read_entries(path: Path) -> list[dict[str, object]]:
    entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if any(not isinstance(entry, dict) for entry in entries):
        raise TypeError
    return entries


def _atomic_write(path: Path, entries: list[dict[str, object]]) -> None:
    descriptor, name = tempfile.mkstemp(prefix=".events-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            for entry in entries:
                stream.write(json.dumps(entry, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _parse_record(data: Any) -> ExecutionRecord | None:
    if not isinstance(data, dict):
        raise TypeError
    if data.get("event") != "execution.completed":
        return None
    fields = data["fields"]
    if not isinstance(fields, dict):
        raise TypeError
    return ExecutionRecord(
        timestamp=_required_string(data, "timestamp"),
        execution_id=_required_string(fields, "execution_id"),
        status=ExecutionStatus(_required_string(fields, "status")),
        exit_code=_optional_int(fields, "exit_code"),
        elapsed_seconds=_optional_number(fields, "elapsed_seconds") or 0.0,
        stdout_reference=_optional_string(fields, "stdout_reference"),
        stderr_reference=_optional_string(fields, "stderr_reference"),
        diagnostic=_optional_string(fields, "diagnostic"),
        targeting=_targeting(fields.get("targeting")),
        mode=ExecutionMode(_optional_string(fields, "mode") or ExecutionMode.CHECK),
        requested_revision=_optional_string(fields, "requested_revision"),
        resolved_revision=_optional_string(fields, "resolved_revision"),
        inventory_digest=_optional_string(fields, "inventory_digest"),
        playbook_digest=_optional_string(fields, "playbook_digest"),
        playbook_path=_optional_string(fields, "playbook_path"),
    )


def _targeting(value: object) -> ExecutionTargeting:
    if value is None:
        return ExecutionTargeting()
    if not isinstance(value, dict):
        raise TypeError
    return ExecutionTargeting(
        limit=_optional_string(value, "limit"),
        tags=_string_tuple(value, "tags"),
        skip_tags=_string_tuple(value, "skip_tags"),
    )


def _string_tuple(data: dict[str, object], key: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TypeError
    return tuple(value)


def _required_string(data: dict[str, object], key: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise TypeError
    return value


def _optional_string(data: dict[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is not None and not isinstance(value, str):
        raise TypeError
    return value


def _optional_int(data: dict[str, object], key: str) -> int | None:
    value = data.get(key)
    if value is not None and (not isinstance(value, int) or isinstance(value, bool)):
        raise TypeError
    return value


def _optional_number(data: dict[str, object], key: str) -> float | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError
    return float(value)

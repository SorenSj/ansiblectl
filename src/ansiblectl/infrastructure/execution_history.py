"""Read safe execution records from the private structured event log."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ansiblectl.domain.errors import ExecutionError
from ansiblectl.domain.execution import ExecutionRecord, ExecutionStatus


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
            lines = path.read_text(encoding="utf-8").splitlines()
            records = [_parse_record(json.loads(line)) for line in lines if line]
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

    def _validated_path(self) -> Path:
        root = self.workspace_root.resolve()
        path = self.path.resolve()
        if not path.is_relative_to(root):
            raise ExecutionError("Execution history must remain inside the selected workspace.")
        return path


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
    )


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

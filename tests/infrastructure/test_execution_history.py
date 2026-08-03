"""Persisted execution-history adapter tests."""

import json
from pathlib import Path

import pytest

from ansiblectl.domain.errors import ExecutionError
from ansiblectl.domain.execution import ExecutionStatus
from ansiblectl.infrastructure.execution_history import JsonLinesExecutionHistory


def _write_events(workspace: Path, records: list[dict[str, object]]) -> None:
    path = workspace / ".ansiblectl" / "logs" / "events.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


def test_history_lists_only_executions_newest_first(tmp_path: Path) -> None:
    _write_events(
        tmp_path,
        [
            {"timestamp": "first", "event": "workspace.initialized", "fields": {}},
            {
                "timestamp": "older",
                "event": "execution.completed",
                "fields": {
                    "execution_id": "run-1",
                    "status": "completed",
                    "exit_code": 0,
                },
            },
            {
                "timestamp": "newer",
                "event": "execution.completed",
                "fields": {
                    "execution_id": "run-2",
                    "status": "timed_out",
                    "exit_code": None,
                    "elapsed_seconds": 30.0,
                    "stdout_reference": "/workspace/.ansiblectl/runs/output.log",
                    "stderr_reference": None,
                    "diagnostic": "Execution exceeded its configured timeout.",
                },
            },
        ],
    )

    records = JsonLinesExecutionHistory(tmp_path).list()

    assert [record.execution_id for record in records] == ["run-2", "run-1"]
    assert records[0].status is ExecutionStatus.TIMED_OUT
    assert records[0].elapsed_seconds == 30.0
    assert records[1].elapsed_seconds == 0.0
    assert JsonLinesExecutionHistory(tmp_path).get("run-1") == records[1]


def test_missing_history_is_empty_and_unknown_execution_is_actionable(tmp_path: Path) -> None:
    history = JsonLinesExecutionHistory(tmp_path)

    assert history.list() == ()
    with pytest.raises(ExecutionError, match="was not found"):
        history.get("missing")


def test_corrupt_history_fails_safely(tmp_path: Path) -> None:
    path = tmp_path / ".ansiblectl" / "logs" / "events.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("not-json\n", encoding="utf-8")

    with pytest.raises(ExecutionError, match="Repair or remove"):
        JsonLinesExecutionHistory(tmp_path).list()


def test_history_symlink_cannot_escape_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside-events.jsonl"
    outside.write_text("", encoding="utf-8")
    path = workspace / ".ansiblectl" / "logs" / "events.jsonl"
    path.parent.mkdir(parents=True)
    path.symlink_to(outside)

    with pytest.raises(ExecutionError, match="remain inside"):
        JsonLinesExecutionHistory(workspace).list()

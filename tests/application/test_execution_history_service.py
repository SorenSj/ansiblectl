"""Execution-history application-service tests."""

from dataclasses import dataclass

import pytest

from ansiblectl.application.execution_history import ExecutionHistoryService
from ansiblectl.domain.errors import ExecutionError
from ansiblectl.domain.execution import (
    ExecutionMode,
    ExecutionRecord,
    ExecutionRetentionResult,
    ExecutionStatus,
)


@dataclass(frozen=True)
class FakeHistoryPort:
    record: ExecutionRecord

    def list(self) -> tuple[ExecutionRecord, ...]:
        return (self.record,)

    def get(self, execution_id: str) -> ExecutionRecord:
        assert execution_id == self.record.execution_id
        return self.record

    def prune(self, keep: int) -> ExecutionRetentionResult:
        assert keep == 0
        return ExecutionRetentionResult(0, (self.record.execution_id,), True)


def test_history_service_delegates_typed_queries() -> None:
    record = ExecutionRecord("timestamp", "run-1", ExecutionStatus.COMPLETED, 0, 0.1)
    service = ExecutionHistoryService(FakeHistoryPort(record))

    assert service.list() == (record,)
    assert service.get("run-1") == record
    assert service.retention(0, apply=False) == ExecutionRetentionResult(0, ("run-1",), False)
    assert service.retention(0, apply=True) == ExecutionRetentionResult(0, ("run-1",), True)
    with pytest.raises(ExecutionError, match="zero or greater"):
        service.retention(-1, apply=False)


def test_history_service_filters_exact_operation_and_rejects_empty_filter() -> None:
    record = ExecutionRecord(
        "timestamp",
        "syntax-1",
        ExecutionStatus.COMPLETED,
        0,
        0.1,
        operation="playbook.syntax_check",
    )
    service = ExecutionHistoryService(FakeHistoryPort(record))

    assert service.list("playbook.syntax_check") == (record,)
    assert service.list("run") == ()
    assert service.list(status=ExecutionStatus.COMPLETED) == (record,)
    assert service.list(status=ExecutionStatus.FAILED) == ()
    assert service.list("playbook.syntax_check", ExecutionStatus.COMPLETED) == (record,)
    assert service.list(mode=ExecutionMode.CHECK) == (record,)
    assert service.list(mode=ExecutionMode.APPLY) == ()
    assert service.list(limit=1) == (record,)
    with pytest.raises(ExecutionError, match="greater than zero"):
        service.list(limit=0)
    with pytest.raises(ExecutionError, match="non-empty"):
        service.list(" ")

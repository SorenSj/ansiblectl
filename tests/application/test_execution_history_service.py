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
    digest = "sha256:" + "a" * 64
    record_with_digest = ExecutionRecord(
        "timestamp",
        "run-2",
        ExecutionStatus.COMPLETED,
        0,
        0.1,
        inventory_digest=digest,
    )
    digest_service = ExecutionHistoryService(FakeHistoryPort(record_with_digest))
    assert digest_service.list(inventory_digest=digest) == (record_with_digest,)
    assert digest_service.list(inventory_digest="sha256:" + "b" * 64) == ()
    with pytest.raises(ExecutionError, match="lowercase sha256"):
        service.list(inventory_digest="sha256:not-a-digest")
    playbook_digest = "sha256:" + "c" * 64
    playbook_record = ExecutionRecord(
        "timestamp",
        "run-3",
        ExecutionStatus.COMPLETED,
        0,
        0.1,
        playbook_digest=playbook_digest,
    )
    playbook_service = ExecutionHistoryService(FakeHistoryPort(playbook_record))
    assert playbook_service.list(playbook_digest=playbook_digest) == (playbook_record,)
    assert playbook_service.list(playbook_digest="sha256:" + "d" * 64) == ()
    with pytest.raises(ExecutionError, match="Playbook digest.*lowercase sha256"):
        service.list(playbook_digest="SHA256:" + "C" * 64)
    revision = "1" * 40
    revision_record = ExecutionRecord(
        "timestamp",
        "run-4",
        ExecutionStatus.COMPLETED,
        0,
        0.1,
        resolved_revision=revision,
    )
    revision_service = ExecutionHistoryService(FakeHistoryPort(revision_record))
    assert revision_service.list(resolved_revision=revision) == (revision_record,)
    assert revision_service.list(resolved_revision="2" * 40) == ()
    with pytest.raises(ExecutionError, match="lowercase Git object"):
        service.list(resolved_revision="main")
    path_record = ExecutionRecord(
        "timestamp",
        "run-5",
        ExecutionStatus.COMPLETED,
        0,
        0.1,
        playbook_path="playbooks/site.yml",
    )
    path_service = ExecutionHistoryService(FakeHistoryPort(path_record))
    assert path_service.list(playbook_path="playbooks/site.yml") == (path_record,)
    assert path_service.list(playbook_path="playbooks/other.yml") == ()
    for invalid_path in ("/site.yml", "../site.yml", "playbooks\\site.yml", "playbooks//site.yml"):
        with pytest.raises(ExecutionError, match="workspace-relative POSIX"):
            service.list(playbook_path=invalid_path)
    assert service.list(limit=1) == (record,)
    with pytest.raises(ExecutionError, match="greater than zero"):
        service.list(limit=0)
    with pytest.raises(ExecutionError, match="non-empty"):
        service.list(" ")

"""Execution-history application-service tests."""

from dataclasses import dataclass

from ansiblectl.application.execution_history import ExecutionHistoryService
from ansiblectl.domain.execution import ExecutionRecord, ExecutionStatus


@dataclass(frozen=True)
class FakeHistoryPort:
    record: ExecutionRecord

    def list(self) -> tuple[ExecutionRecord, ...]:
        return (self.record,)

    def get(self, execution_id: str) -> ExecutionRecord:
        assert execution_id == self.record.execution_id
        return self.record


def test_history_service_delegates_typed_queries() -> None:
    record = ExecutionRecord("timestamp", "run-1", ExecutionStatus.COMPLETED, 0, 0.1)
    service = ExecutionHistoryService(FakeHistoryPort(record))

    assert service.list() == (record,)
    assert service.get("run-1") == record

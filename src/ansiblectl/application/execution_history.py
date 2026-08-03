"""Execution-history inspection use cases."""

from dataclasses import dataclass

from ansiblectl.domain.errors import ExecutionError
from ansiblectl.domain.execution import (
    ExecutionHistoryPort,
    ExecutionRecord,
    ExecutionRetentionResult,
    ExecutionStatus,
)


@dataclass(frozen=True)
class ExecutionHistoryService:
    port: ExecutionHistoryPort

    def list(
        self,
        operation: str | None = None,
        status: ExecutionStatus | None = None,
    ) -> tuple[ExecutionRecord, ...]:
        records = self.port.list()
        if operation is not None:
            if not operation.strip():
                raise ExecutionError("Execution operation filter must be non-empty.")
            records = tuple(record for record in records if record.operation == operation)
        if status is not None:
            records = tuple(record for record in records if record.status is status)
        return records

    def get(self, execution_id: str) -> ExecutionRecord:
        return self.port.get(execution_id)

    def retention(self, keep: int, *, apply: bool) -> ExecutionRetentionResult:
        if keep < 0:
            raise ExecutionError("Execution retention count must be zero or greater.")
        if apply:
            return self.port.prune(keep)
        records = self.port.list()
        return ExecutionRetentionResult(
            min(keep, len(records)), tuple(record.execution_id for record in records[keep:]), False
        )

"""Execution-history inspection use cases."""

from dataclasses import dataclass

from ansiblectl.domain.errors import ExecutionError
from ansiblectl.domain.execution import (
    ExecutionHistoryPort,
    ExecutionRecord,
    ExecutionRetentionResult,
)


@dataclass(frozen=True)
class ExecutionHistoryService:
    port: ExecutionHistoryPort

    def list(self) -> tuple[ExecutionRecord, ...]:
        return self.port.list()

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

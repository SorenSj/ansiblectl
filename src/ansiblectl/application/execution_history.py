"""Execution-history inspection use cases."""

from dataclasses import dataclass

from ansiblectl.domain.execution import ExecutionHistoryPort, ExecutionRecord


@dataclass(frozen=True)
class ExecutionHistoryService:
    port: ExecutionHistoryPort

    def list(self) -> tuple[ExecutionRecord, ...]:
        return self.port.list()

    def get(self, execution_id: str) -> ExecutionRecord:
        return self.port.get(execution_id)

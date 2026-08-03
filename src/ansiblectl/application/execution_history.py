"""Execution-history inspection use cases."""

from dataclasses import dataclass

from ansiblectl.domain.errors import ExecutionError
from ansiblectl.domain.execution import (
    ExecutionHistoryPort,
    ExecutionMode,
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
        mode: ExecutionMode | None = None,
        inventory_digest: str | None = None,
        playbook_digest: str | None = None,
        limit: int | None = None,
    ) -> tuple[ExecutionRecord, ...]:
        records = self.port.list()
        if operation is not None:
            if not operation.strip():
                raise ExecutionError("Execution operation filter must be non-empty.")
            records = tuple(record for record in records if record.operation == operation)
        if status is not None:
            records = tuple(record for record in records if record.status is status)
        if mode is not None:
            records = tuple(record for record in records if record.mode is mode)
        if inventory_digest is not None:
            if not _is_canonical_sha256(inventory_digest):
                raise ExecutionError("Inventory digest filter must be a lowercase sha256: value.")
            records = tuple(
                record for record in records if record.inventory_digest == inventory_digest
            )
        if playbook_digest is not None:
            if not _is_canonical_sha256(playbook_digest):
                raise ExecutionError("Playbook digest filter must be a lowercase sha256: value.")
            records = tuple(
                record for record in records if record.playbook_digest == playbook_digest
            )
        if limit is not None:
            if limit <= 0:
                raise ExecutionError("Execution result limit must be greater than zero.")
            records = records[:limit]
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


def _is_canonical_sha256(value: str) -> bool:
    digest = value.removeprefix("sha256:")
    return (
        value.startswith("sha256:")
        and len(digest) == 64
        and all(character in "0123456789abcdef" for character in digest)
    )

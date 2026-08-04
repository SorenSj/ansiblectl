"""Bounded read-only snapshot use case for the local terminal dashboard."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from ansiblectl.application.execution_history import ExecutionSummary
from ansiblectl.application.status import Status
from ansiblectl.domain.durable_events import DurableConsumerStatus
from ansiblectl.domain.errors import AnsiblectlError
from ansiblectl.domain.execution import ExecutionMode, ExecutionRecord, ExecutionStatus

MAX_DASHBOARD_EXECUTIONS = 100
MAX_DASHBOARD_CONSUMERS = 100


class DashboardSnapshotError(AnsiblectlError):
    """A value-free failure to construct one complete dashboard snapshot."""


@dataclass(frozen=True)
class DashboardCount:
    """One canonical named count."""

    name: str
    count: int


@dataclass(frozen=True)
class DashboardExecutionRow:
    """Allowlisted execution metadata safe for dashboard presentation."""

    timestamp: str
    execution_id: str
    status: str
    operation: str
    mode: str
    exit_code: int | None
    elapsed_seconds: float


@dataclass(frozen=True)
class DashboardConsumerRow:
    """Payload-free durable-consumer state safe for dashboard presentation."""

    consumer_id: str
    event_count: int
    pending_count: int
    lowest_pending_sequence: int | None
    attempt_count: int
    next_attempt_at: str | None
    state: str


@dataclass(frozen=True)
class DashboardSnapshot:
    """One complete immutable dashboard snapshot."""

    version: str
    message: str
    execution_total: int
    execution_status_counts: tuple[DashboardCount, ...]
    execution_mode_counts: tuple[DashboardCount, ...]
    executions: tuple[DashboardExecutionRow, ...]
    consumers: tuple[DashboardConsumerRow, ...]


@dataclass(frozen=True)
class DashboardQueries:
    """Closed query capability set available to the dashboard use case."""

    status: Callable[[], Status]
    execution_summary: Callable[[], ExecutionSummary]
    executions: Callable[..., tuple[ExecutionRecord, ...]]
    consumers: Callable[[], tuple[DurableConsumerStatus, ...]]


@dataclass(frozen=True)
class DashboardSnapshotService:
    """Construct complete snapshots without retaining partial query results."""

    queries: DashboardQueries

    def snapshot(self) -> DashboardSnapshot:
        """Return one bounded snapshot or one stable value-free failure."""

        try:
            status = self.queries.status()
            summary = self.queries.execution_summary()
            executions = self.queries.executions(limit=MAX_DASHBOARD_EXECUTIONS)
            consumers = self.queries.consumers()
            return _build_snapshot(status, summary, executions, consumers)
        except DashboardSnapshotError:
            raise
        except Exception as error:
            raise DashboardSnapshotError(
                "Dashboard snapshot is unavailable.", cause=error
            ) from error


def _build_snapshot(
    status: Status,
    summary: ExecutionSummary,
    executions: tuple[ExecutionRecord, ...],
    consumers: tuple[DurableConsumerStatus, ...],
) -> DashboardSnapshot:
    if not isinstance(status.version, str) or not isinstance(status.message, str):
        raise DashboardSnapshotError("Dashboard snapshot is unavailable.")
    total = _non_negative_int(summary.total)
    status_counts = _canonical_counts(summary.by_status, tuple(ExecutionStatus))
    mode_counts = _canonical_counts(summary.by_mode, tuple(ExecutionMode))
    if not isinstance(executions, tuple) or len(executions) > MAX_DASHBOARD_EXECUTIONS:
        raise DashboardSnapshotError("Dashboard snapshot is unavailable.")
    if not isinstance(consumers, tuple) or len(consumers) > MAX_DASHBOARD_CONSUMERS:
        raise DashboardSnapshotError("Dashboard snapshot is unavailable.")
    return DashboardSnapshot(
        version=status.version,
        message=status.message,
        execution_total=total,
        execution_status_counts=status_counts,
        execution_mode_counts=mode_counts,
        executions=tuple(_execution_row(record) for record in executions),
        consumers=tuple(_consumer_row(consumer) for consumer in consumers),
    )


def _canonical_counts(
    values: Mapping[str, int], names: tuple[ExecutionStatus | ExecutionMode, ...]
) -> tuple[DashboardCount, ...]:
    if not isinstance(values, Mapping):
        raise DashboardSnapshotError("Dashboard snapshot is unavailable.")
    return tuple(
        DashboardCount(name.value, _non_negative_int(values[name.value])) for name in names
    )


def _execution_row(record: ExecutionRecord) -> DashboardExecutionRow:
    if not isinstance(record, ExecutionRecord):
        raise DashboardSnapshotError("Dashboard snapshot is unavailable.")
    elapsed = record.elapsed_seconds
    if (
        not isinstance(elapsed, (int, float))
        or isinstance(elapsed, bool)
        or not math.isfinite(elapsed)
        or elapsed < 0
    ):
        raise DashboardSnapshotError("Dashboard snapshot is unavailable.")
    if record.exit_code is not None and (
        not isinstance(record.exit_code, int) or isinstance(record.exit_code, bool)
    ):
        raise DashboardSnapshotError("Dashboard snapshot is unavailable.")
    if not all(
        isinstance(value, str)
        for value in (record.timestamp, record.execution_id, record.operation)
    ):
        raise DashboardSnapshotError("Dashboard snapshot is unavailable.")
    if not isinstance(record.status, ExecutionStatus) or not isinstance(record.mode, ExecutionMode):
        raise DashboardSnapshotError("Dashboard snapshot is unavailable.")
    return DashboardExecutionRow(
        timestamp=record.timestamp,
        execution_id=record.execution_id,
        status=record.status.value,
        operation=record.operation,
        mode=record.mode.value,
        exit_code=record.exit_code,
        elapsed_seconds=float(elapsed),
    )


def _consumer_row(consumer: DurableConsumerStatus) -> DashboardConsumerRow:
    if not isinstance(consumer, DurableConsumerStatus):
        raise DashboardSnapshotError("Dashboard snapshot is unavailable.")
    if not all(isinstance(value, str) for value in (consumer.consumer_id, consumer.state)) or (
        consumer.next_attempt_at is not None and not isinstance(consumer.next_attempt_at, str)
    ):
        raise DashboardSnapshotError("Dashboard snapshot is unavailable.")
    return DashboardConsumerRow(
        consumer_id=consumer.consumer_id,
        event_count=_non_negative_int(consumer.event_count),
        pending_count=_non_negative_int(consumer.pending_count),
        lowest_pending_sequence=_optional_non_negative_int(consumer.lowest_pending_sequence),
        attempt_count=_non_negative_int(consumer.attempt_count),
        next_attempt_at=consumer.next_attempt_at,
        state=consumer.state,
    )


def _non_negative_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DashboardSnapshotError("Dashboard snapshot is unavailable.")
    return value


def _optional_non_negative_int(value: object) -> int | None:
    if value is None:
        return None
    return _non_negative_int(value)


__all__ = [
    "DashboardConsumerRow",
    "DashboardCount",
    "DashboardExecutionRow",
    "DashboardQueries",
    "DashboardSnapshot",
    "DashboardSnapshotError",
    "DashboardSnapshotService",
    "MAX_DASHBOARD_CONSUMERS",
    "MAX_DASHBOARD_EXECUTIONS",
]

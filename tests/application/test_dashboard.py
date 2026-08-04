"""Read-only dashboard snapshot application tests."""

from collections.abc import Callable
from dataclasses import replace

import pytest

from ansiblectl.application.dashboard import (
    DashboardQueries,
    DashboardSnapshotError,
    DashboardSnapshotService,
)
from ansiblectl.application.execution_history import ExecutionSummary
from ansiblectl.application.status import Status
from ansiblectl.domain.durable_events import DurableConsumerStatus
from ansiblectl.domain.execution import ExecutionRecord, ExecutionStatus


def _record() -> ExecutionRecord:
    return ExecutionRecord(
        "2026-08-04T06:00:00.000000Z",
        "run-1",
        ExecutionStatus.COMPLETED,
        0,
        1.25,
        stdout_reference="forbidden-stdout",
        stderr_reference="forbidden-stderr",
        diagnostic="forbidden-diagnostic",
        requested_revision="forbidden-requested",
        resolved_revision="forbidden-resolved",
        inventory_digest="forbidden-inventory",
        playbook_digest="forbidden-playbook",
        playbook_path="forbidden/path.yml",
        verbosity=4,
        diff=True,
        operation="run",
    )


def _queries(
    *,
    status: Callable[[], Status] | None = None,
    summary: Callable[[], ExecutionSummary] | None = None,
    executions: Callable[..., tuple[ExecutionRecord, ...]] | None = None,
    consumers: Callable[[], tuple[DurableConsumerStatus, ...]] | None = None,
) -> DashboardQueries:
    return DashboardQueries(
        status or (lambda: Status("0.17.0", "Ansiblectl is ready.")),
        summary
        or (
            lambda: ExecutionSummary(
                1,
                {"cancelled": 0, "completed": 1, "failed": 0, "timed_out": 0},
                {"apply": 0, "check": 1},
                {"forbidden-operation-summary": 99},
            )
        ),
        executions or (lambda *, limit: (_record(),) if limit == 100 else ()),
        consumers or (lambda: (DurableConsumerStatus("audit", 3, 1, 3, 2, None, "retry_wait"),)),
    )


def test_snapshot_uses_exact_query_order_and_allowlisted_fields() -> None:
    calls: list[str] = []

    def status() -> Status:
        calls.append("status")
        return Status("0.17.0", "Ansiblectl is ready.")

    def summary() -> ExecutionSummary:
        calls.append("summary")
        return ExecutionSummary(
            1,
            {"cancelled": 0, "completed": 1, "failed": 0, "timed_out": 0},
            {"apply": 0, "check": 1},
            {"forbidden": 1},
        )

    def executions(*, limit: int) -> tuple[ExecutionRecord, ...]:
        calls.append(f"executions:{limit}")
        return (_record(),)

    def consumers() -> tuple[DurableConsumerStatus, ...]:
        calls.append("consumers")
        return (DurableConsumerStatus("audit", 3, 1, 3, 2, None, "retry_wait"),)

    snapshot = DashboardSnapshotService(
        DashboardQueries(status, summary, executions, consumers)
    ).snapshot()

    assert calls == ["status", "summary", "executions:100", "consumers"]
    assert snapshot.version == "0.17.0"
    assert snapshot.execution_total == 1
    assert [(item.name, item.count) for item in snapshot.execution_status_counts] == [
        ("completed", 1),
        ("failed", 0),
        ("timed_out", 0),
        ("cancelled", 0),
    ]
    assert [(item.name, item.count) for item in snapshot.execution_mode_counts] == [
        ("check", 1),
        ("apply", 0),
    ]
    assert snapshot.executions[0].__dict__ == {
        "timestamp": "2026-08-04T06:00:00.000000Z",
        "execution_id": "run-1",
        "status": "completed",
        "operation": "run",
        "mode": "check",
        "exit_code": 0,
        "elapsed_seconds": 1.25,
    }
    assert snapshot.consumers[0].__dict__ == {
        "consumer_id": "audit",
        "event_count": 3,
        "pending_count": 1,
        "lowest_pending_sequence": 3,
        "attempt_count": 2,
        "next_attempt_at": None,
        "state": "retry_wait",
    }
    rendered = repr(snapshot)
    for forbidden in (
        "forbidden-stdout",
        "forbidden-stderr",
        "forbidden-diagnostic",
        "forbidden-requested",
        "forbidden-resolved",
        "forbidden-inventory",
        "forbidden-playbook",
        "forbidden/path.yml",
        "forbidden-operation-summary",
    ):
        assert forbidden not in rendered


def test_snapshot_enforces_both_row_bounds() -> None:
    records = tuple(replace(_record(), execution_id=f"run-{index}") for index in range(101))
    consumers = tuple(
        DurableConsumerStatus(f"sink-{index}", 0, 0, None, 0, None, "idle") for index in range(101)
    )

    with pytest.raises(DashboardSnapshotError, match="snapshot is unavailable"):
        DashboardSnapshotService(_queries(executions=lambda *, limit: records)).snapshot()
    with pytest.raises(DashboardSnapshotError, match="snapshot is unavailable"):
        DashboardSnapshotService(_queries(consumers=lambda: consumers)).snapshot()


@pytest.mark.parametrize(
    ("summary", "record", "consumer"),
    [
        (
            ExecutionSummary(-1, {}, {}, {}),
            _record(),
            DurableConsumerStatus("sink", 0, 0, None, 0, None, "idle"),
        ),
        (
            ExecutionSummary(
                1,
                {"cancelled": 0, "completed": 1, "failed": 0, "timed_out": 0},
                {"apply": 0, "check": 1},
                {},
            ),
            replace(_record(), elapsed_seconds=float("nan")),
            DurableConsumerStatus("sink", 0, 0, None, 0, None, "idle"),
        ),
        (
            ExecutionSummary(
                1,
                {"cancelled": 0, "completed": 1, "failed": 0, "timed_out": 0},
                {"apply": 0, "check": 1},
                {},
            ),
            _record(),
            DurableConsumerStatus("sink", -1, 0, None, 0, None, "idle"),
        ),
    ],
)
def test_snapshot_rejects_invalid_safe_metadata(
    summary: ExecutionSummary,
    record: ExecutionRecord,
    consumer: DurableConsumerStatus,
) -> None:
    with pytest.raises(DashboardSnapshotError, match="snapshot is unavailable"):
        DashboardSnapshotService(
            _queries(
                summary=lambda: summary,
                executions=lambda *, limit: (record,),
                consumers=lambda: (consumer,),
            )
        ).snapshot()


def test_query_failures_are_value_free_and_stop_later_queries() -> None:
    calls: list[str] = []

    def fail() -> ExecutionSummary:
        calls.append("summary")
        raise RuntimeError("forbidden-secret-value")

    def executions(*, limit: int) -> tuple[ExecutionRecord, ...]:
        calls.append("executions")
        return ()

    with pytest.raises(DashboardSnapshotError) as raised:
        DashboardSnapshotService(_queries(summary=fail, executions=executions)).snapshot()

    assert calls == ["summary"]
    assert str(raised.value) == "Dashboard snapshot is unavailable."
    assert "forbidden-secret-value" not in repr(raised.value)

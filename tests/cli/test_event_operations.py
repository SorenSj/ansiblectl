"""Durable-event operator CLI contract tests."""

import json
from io import StringIO
from pathlib import Path

import yaml

from ansiblectl.application.event_operations import EventOperationsService
from ansiblectl.cli.composition import build_workspace_service
from ansiblectl.cli.main import EXIT_SUCCESS, cli, main
from ansiblectl.domain.durable_events import (
    DurableConsumerStatus,
    DurableEventActionResult,
    DurableEventRetentionResult,
)
from ansiblectl.domain.event_delivery import DeliveryRunResult, DeliveryRunState
from ansiblectl.domain.workspace import Workspace
from ansiblectl.infrastructure.event_outbox import SqliteEventOutbox


class WorkspaceService:
    def resolve(self, explicit_path: Path | None, current_directory: Path) -> Workspace:
        root = (explicit_path or current_directory).resolve()
        return Workspace(root, root / ".ansiblectl/workspace.json", 1)


class EventPort:
    def __init__(self) -> None:
        self.registered = False

    def register_consumer(self, consumer_id: str, *, start_sequence: int = 1) -> bool:
        changed = not self.registered
        self.registered = True
        return changed

    def inspect_consumers(self) -> tuple[DurableConsumerStatus, ...]:
        return (DurableConsumerStatus("sink", 4, 2, 3, 1, None, "blocked"),)

    def retry(self, consumer_id: str, *, sequence: int, event_id: str) -> None:
        return None

    def abandon(
        self, consumer_id: str, *, sequence: int, event_id: str, apply: bool = False
    ) -> DurableEventActionResult:
        return DurableEventActionResult(consumer_id, sequence, event_id, apply)

    def retain(self, *, apply: bool = False) -> DurableEventRetentionResult:
        return DurableEventRetentionResult(2, 2, apply)


class DeliveryService:
    def __init__(self, result: DeliveryRunResult) -> None:
        self.result = result
        self.calls: list[tuple[str, int]] = []

    def run(self, consumer_id: str, *, max_events: int) -> DeliveryRunResult:
        self.calls.append((consumer_id, max_events))
        return self.result


def invoke(arguments: list[str], service: EventOperationsService) -> dict[str, object]:
    output = StringIO()
    result = main(
        ["--workspace", ".", "--output-format", "json", *arguments],
        workspace_service=WorkspaceService(),  # type: ignore[arg-type]
        event_operations_service=service,
        stdout=output,
    )
    assert result == EXIT_SUCCESS
    value = json.loads(output.getvalue())
    assert isinstance(value, dict)
    return value


def test_consumer_commands_are_exact_and_payload_free() -> None:
    service = EventOperationsService(EventPort())

    registered = invoke(["event", "consumer", "register", "sink", "--start-sequence", "3"], service)
    inspected = invoke(["event", "consumer", "inspect"], service)
    retried = invoke(
        ["event", "consumer", "retry", "sink", "--sequence", "3", "--event-id", "event-3"],
        service,
    )

    assert registered == {
        "applied": True,
        "consumer_id": "sink",
        "schema_version": 1,
        "start_sequence": 3,
    }
    assert inspected["consumers"] == [
        {
            "attempt_count": 1,
            "consumer_id": "sink",
            "event_count": 4,
            "lowest_pending_sequence": 3,
            "next_attempt_at": None,
            "pending_count": 2,
            "state": "blocked",
        }
    ]
    assert retried["applied"] is True
    assert retried["event_id"] == "event-3"


def test_destructive_commands_preview_before_apply() -> None:
    service = EventOperationsService(EventPort())
    target = ["event", "consumer", "abandon", "sink", "--sequence", "3", "--event-id", "event-3"]

    assert invoke(target, service)["applied"] is False
    assert invoke([*target, "--apply"], service)["applied"] is True
    assert invoke(["event", "retention"], service)["applied"] is False
    assert invoke(["event", "retention", "--apply"], service)["applied"] is True


def test_human_consumer_inspection_is_readable() -> None:
    output = StringIO()
    result = main(
        ["--workspace", ".", "event", "consumer", "inspect"],
        workspace_service=WorkspaceService(),  # type: ignore[arg-type]
        event_operations_service=EventOperationsService(EventPort()),
        stdout=output,
    )

    assert result == EXIT_SUCCESS
    assert output.getvalue() == "sink: blocked; 2 pending; next sequence 3\n"


def test_delivery_command_is_bounded_exact_targeted_and_payload_free() -> None:
    output = StringIO()
    delivery = DeliveryService(
        DeliveryRunResult(
            "audit",
            DeliveryRunState.DELIVERED,
            2,
            0,
            "00000000Z80000000000000000",
            2,
            None,
        )
    )

    result = main(
        [
            "--workspace",
            ".",
            "--output-format",
            "json",
            "event",
            "deliver",
            "audit",
            "--endpoint",
            "primary",
            "--max-events",
            "2",
        ],
        workspace_service=WorkspaceService(),  # type: ignore[arg-type]
        event_delivery_service=delivery,  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_SUCCESS
    assert delivery.calls == [("audit", 2)]
    assert json.loads(output.getvalue()) == {
        "consumer_id": "audit",
        "delivered_count": 2,
        "failed_count": 0,
        "failure_reason": None,
        "last_event_id": "00000000Z80000000000000000",
        "last_sequence": 2,
        "schema_version": 1,
        "state": "delivered",
    }


def test_delivery_command_rejects_unbounded_count_before_service_call() -> None:
    output = StringIO()
    errors = StringIO()
    delivery = DeliveryService(
        DeliveryRunResult("audit", DeliveryRunState.IDLE, 0, 0, None, None, None)
    )

    result = main(
        [
            "--workspace",
            ".",
            "--output-format",
            "json",
            "event",
            "deliver",
            "audit",
            "--endpoint",
            "primary",
            "--max-events",
            "101",
        ],
        workspace_service=WorkspaceService(),  # type: ignore[arg-type]
        event_delivery_service=delivery,  # type: ignore[arg-type]
        stdout=output,
        stderr=errors,
    )

    assert result != EXIT_SUCCESS
    assert delivery.calls == []
    assert "between 1 and 100" in output.getvalue()
    assert errors.getvalue() == ""


def test_delivery_yaml_envelope_is_schema_aligned_and_stays_idle_without_network(
    tmp_path: Path,
) -> None:
    build_workspace_service().initialize(tmp_path)
    SqliteEventOutbox(tmp_path).register_consumer("audit", start_sequence=2)
    (tmp_path / ".ansiblectl/webhooks.yaml").write_text(
        """schema_version: 1
endpoints:
  primary:
    url: https://hooks.example.test/events
    allowed_hostnames: [hooks.example.test]
""",
        encoding="utf-8",
    )
    output = StringIO()

    result = cli(
        [
            "--workspace",
            str(tmp_path),
            "--output",
            "yaml",
            "event",
            "deliver",
            "audit",
            "--endpoint",
            "primary",
            "--max-events",
            "1",
        ],
        stdout=output,
    )

    payload = yaml.safe_load(output.getvalue())
    assert result == EXIT_SUCCESS
    assert payload["command"] == "event deliver"
    assert payload["data"]["state"] == "idle"
    assert payload["data"]["schema_version"] == 1
    assert payload["data"]["delivered_count"] == 0

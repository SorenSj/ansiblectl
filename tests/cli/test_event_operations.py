"""Durable-event operator CLI contract tests."""

import json
from io import StringIO
from pathlib import Path

from ansiblectl.application.event_operations import EventOperationsService
from ansiblectl.cli.main import EXIT_SUCCESS, main
from ansiblectl.domain.durable_events import (
    DurableConsumerStatus,
    DurableEventActionResult,
    DurableEventRetentionResult,
)
from ansiblectl.domain.workspace import Workspace


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

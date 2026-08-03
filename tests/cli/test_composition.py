"""Concrete CLI composition tests."""

from pathlib import Path

from ansiblectl.cli.composition import build_run_service
from ansiblectl.infrastructure.json_logging import EventLogSubscriber, JsonLinesLogSink


def test_run_service_wires_execution_events_to_workspace_log(tmp_path: Path) -> None:
    service = build_run_service(tmp_path)

    assert service.execution.events is not None
    subscriber = service.execution.events.subscribers[0]
    assert isinstance(subscriber, EventLogSubscriber)
    assert isinstance(subscriber.sink, JsonLinesLogSink)
    assert subscriber.sink.path == tmp_path / ".ansiblectl" / "logs" / "events.jsonl"

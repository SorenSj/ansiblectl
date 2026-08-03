"""Structured JSON Lines logging tests."""

import json
import stat
from pathlib import Path

from ansiblectl.domain.events import Event, EventBus
from ansiblectl.infrastructure.json_logging import EventLogSubscriber, JsonLinesLogSink


def test_execution_event_is_appended_as_private_correlated_json(tmp_path: Path) -> None:
    path = tmp_path / ".ansiblectl" / "logs" / "events.jsonl"
    bus = EventBus([EventLogSubscriber(JsonLinesLogSink(tmp_path))])

    bus.publish(
        Event(
            "execution.completed",
            {"execution_id": "run-1", "status": "completed", "token": "hidden"},
        )
    )

    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["event"] == "execution.completed"
    assert record["correlation_id"] == "run-1"
    assert record["fields"] == {
        "execution_id": "run-1",
        "status": "completed",
        "token": "<redacted>",
    }
    assert "hidden" not in path.read_text(encoding="utf-8")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.parent.parent.stat().st_mode) == 0o700


def test_sink_appends_one_record_per_line(tmp_path: Path) -> None:
    path = tmp_path / ".ansiblectl" / "logs" / "events.jsonl"
    sink = JsonLinesLogSink(tmp_path)

    sink.emit({"event": "first"})
    sink.emit({"event": "second"})

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert records == [{"event": "first"}, {"event": "second"}]

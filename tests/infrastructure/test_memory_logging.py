"""Sink redaction tests."""

from ansiblectl.domain.logging import LogEvent, emit
from ansiblectl.infrastructure.memory_logging import MemoryLogSink


def test_sink_receives_only_redacted_records() -> None:
    sink = MemoryLogSink()
    emit(sink, LogEvent("info", "plugin.event", {"password": "secret"}, "run-1"))
    assert "secret" not in str(sink.records)

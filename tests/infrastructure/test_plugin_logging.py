"""Plugin logging adapter tests."""

from ansiblectl.infrastructure.memory_logging import MemoryLogSink
from ansiblectl.infrastructure.plugin_logging import PluginLogAdapter


def test_plugin_logs_include_identity_correlation_and_redaction() -> None:
    sink = MemoryLogSink()
    PluginLogAdapter("demo", sink).emit(
        level="info", name="provider.ready", fields={"token": "hidden"}, correlation_id="run-1"
    )

    assert sink.records == [
        {
            "timestamp": sink.records[0]["timestamp"],
            "level": "info",
            "event": "provider.ready",
            "correlation_id": "run-1",
            "fields": {"token": "<redacted>", "plugin_identity": "demo"},
        }
    ]

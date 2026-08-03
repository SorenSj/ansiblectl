"""Structured logging tests."""

from ansiblectl.domain.logging import LogEvent


def test_event_has_mandatory_fields_and_redacts_secret_values() -> None:
    event = LogEvent("info", "execution.started", {"token": "hidden", "plugin": "demo"}, "exec-1")
    record = event.redacted()
    assert record["correlation_id"] == "exec-1"
    assert record["fields"] == {"token": "<redacted>", "plugin": "demo"}
    assert "hidden" not in str(record)

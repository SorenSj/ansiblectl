"""Production whole-second webhook clock tests."""

import pytest

from ansiblectl.infrastructure.system_webhook_clock import SystemWebhookClock


def test_system_clock_uses_integer_nanoseconds_without_fractional_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("time.time_ns", lambda: 1_234_567_890_123_456_789)

    assert SystemWebhookClock().now_unix_seconds() == 1_234_567_890

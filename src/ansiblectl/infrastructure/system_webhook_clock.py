"""Production UTC clock for timestamp-bound webhook attempts."""

from __future__ import annotations

import time


class SystemWebhookClock:
    """Return current Unix time with explicit whole-second precision."""

    def now_unix_seconds(self) -> int:
        return time.time_ns() // 1_000_000_000


__all__ = ["SystemWebhookClock"]

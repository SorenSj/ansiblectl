"""Private JSON Lines sink for structured local observability."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ansiblectl.domain.events import Event
from ansiblectl.domain.logging import LogEvent, LogSink, emit


@dataclass(frozen=True)
class JsonLinesLogSink:
    """Append structured records to an owner-only JSON Lines file."""

    workspace_root: Path

    @property
    def path(self) -> Path:
        return self.workspace_root / ".ansiblectl" / "logs" / "events.jsonl"

    def emit(self, record: Mapping[str, object]) -> None:
        private_root = self.workspace_root / ".ansiblectl"
        for directory in (private_root, self.path.parent):
            directory.mkdir(mode=0o700, exist_ok=True)
            directory.chmod(0o700)
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(self.path, flags, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as output_file:
            output_file.write(json.dumps(dict(record), sort_keys=True) + "\n")
        self.path.chmod(0o600)


@dataclass(frozen=True)
class EventLogSubscriber:
    """Translate a safe public event into a correlated structured log record."""

    sink: LogSink

    def __call__(self, event: Event) -> None:
        execution_id = event.payload.get("execution_id")
        correlation_id = execution_id if isinstance(execution_id, str) else None
        emit(self.sink, LogEvent("info", event.name, event.payload, correlation_id))

"""Public plugin logger contract."""

from typing import Protocol

from ansiblectl.domain.logging import LogEvent


class PluginLogger(Protocol):
    def emit(self, event: LogEvent) -> None: ...

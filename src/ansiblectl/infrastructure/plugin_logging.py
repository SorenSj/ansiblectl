"""Safe bridge from the public plugin logger contract to core log sinks."""

from collections.abc import Mapping
from dataclasses import dataclass

from ansiblectl.domain.logging import LogEvent, LogSink, emit


@dataclass(frozen=True)
class PluginLogAdapter:
    plugin_identity: str
    sink: LogSink

    def emit(
        self,
        *,
        level: str,
        name: str,
        fields: Mapping[str, object] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        event_fields = {**(fields or {}), "plugin_identity": self.plugin_identity}
        emit(self.sink, LogEvent(level, name, event_fields, correlation_id))

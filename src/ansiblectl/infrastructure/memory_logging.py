"""Memory log sink for tests and local inspection."""

from dataclasses import dataclass, field

from ansiblectl.domain.logging import LogEvent


@dataclass
class MemoryLogSink:
    records: list[dict[str, object]] = field(default_factory=list)

    def emit(self, event: LogEvent) -> None:
        self.records.append(event.redacted())

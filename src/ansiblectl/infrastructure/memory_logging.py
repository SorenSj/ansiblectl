"""Memory log sink for tests and local inspection."""

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass
class MemoryLogSink:
    records: list[dict[str, object]] = field(default_factory=list)

    def emit(self, record: Mapping[str, object]) -> None:
        self.records.append(dict(record))

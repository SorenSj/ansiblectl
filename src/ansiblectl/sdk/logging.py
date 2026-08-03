"""Public plugin logger contract."""

from collections.abc import Mapping
from typing import Protocol


class PluginLogger(Protocol):
    """The SDK-only contract through which plugins emit structured log events."""

    def emit(
        self,
        *,
        level: str,
        name: str,
        fields: Mapping[str, object] | None = None,
        correlation_id: str | None = None,
    ) -> None: ...

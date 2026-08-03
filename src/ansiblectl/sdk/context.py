"""Public, capability-scoped plugin SDK context."""

from dataclasses import dataclass

SDK_VERSION = "0.1"


@dataclass(frozen=True)
class SDKContext:
    """Stable context that exposes granted capabilities only."""

    granted_capabilities: frozenset[str]

    def has_capability(self, name: str) -> bool:
        return name in self.granted_capabilities

"""Atomic plugin lifecycle runtime; third-party code receives SDK context only."""

from dataclasses import dataclass, field
from typing import Protocol

from ansiblectl.domain.plugins import ProviderDescriptor


@dataclass(frozen=True)
class PluginContext:
    granted_capabilities: frozenset[str]


class Plugin(Protocol):
    def initialize(self, context: PluginContext) -> tuple[str, ...]: ...

    def shutdown(self) -> None: ...


@dataclass
class PluginRuntime:
    registered_capabilities: dict[str, tuple[str, ...]] = field(default_factory=dict)
    diagnostics: list[str] = field(default_factory=list)
    _initialized: list[Plugin] = field(default_factory=list)

    def load(
        self, descriptor: ProviderDescriptor, plugin: Plugin, granted_capabilities: frozenset[str]
    ) -> bool:
        try:
            capabilities = plugin.initialize(PluginContext(granted_capabilities))
        except Exception as error:
            self.diagnostics.append(
                f"Optional plugin '{descriptor.identity}' failed: {error.__class__.__name__}."
            )
            return False
        self.registered_capabilities[descriptor.identity] = capabilities
        self._initialized.append(plugin)
        return True

    def shutdown(self) -> None:
        for plugin in reversed(self._initialized):
            plugin.shutdown()
        self._initialized.clear()

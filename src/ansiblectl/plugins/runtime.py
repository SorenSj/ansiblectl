"""Atomic plugin lifecycle runtime; third-party code receives SDK context only."""

from dataclasses import dataclass, field
from typing import Protocol

from ansiblectl.domain.permissions import PermissionDeniedError, resolve_permissions
from ansiblectl.domain.plugins import ProviderDescriptor
from ansiblectl.sdk.context import SDKContext


class Plugin(Protocol):
    def initialize(self, context: SDKContext) -> tuple[str, ...]: ...

    def shutdown(self) -> None: ...


@dataclass
class PluginRuntime:
    registered_capabilities: dict[str, tuple[str, ...]] = field(default_factory=dict)
    diagnostics: list[str] = field(default_factory=list)
    _initialized: list[Plugin] = field(default_factory=list)

    def load(
        self, descriptor: ProviderDescriptor, plugin: Plugin, policy_grants: frozenset[str]
    ) -> bool:
        try:
            decision = resolve_permissions(descriptor.permissions, policy_grants)
        except PermissionDeniedError as error:
            self.diagnostics.append(
                f"Optional plugin '{descriptor.identity}' failed: {error.__class__.__name__}."
            )
            return False
        for permission in sorted(decision.denied):
            self.diagnostics.append(
                f"Plugin '{descriptor.identity}' denied permission '{permission}' by policy."
            )
        try:
            capabilities = plugin.initialize(SDKContext(decision.granted))
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

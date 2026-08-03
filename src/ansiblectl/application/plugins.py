"""Plugin discovery use case."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from ansiblectl.domain.permissions import (
    CAPABILITY_PERMISSIONS,
    PermissionDeniedError,
    resolve_permissions,
)
from ansiblectl.domain.plugins import PluginManifestError, ProviderDescriptor, register_descriptors


@dataclass(frozen=True)
class PluginPermissionReport:
    """Safe permission preflight for one validated provider descriptor."""

    identity: str
    requested: tuple[str, ...]
    granted: tuple[str, ...]
    denied: tuple[str, ...]


@dataclass(frozen=True)
class PluginPermissionService:
    """Resolve explicit policy grants without loading plugin code."""

    def evaluate(
        self, descriptor: ProviderDescriptor, policy_grants: frozenset[str]
    ) -> PluginPermissionReport:
        unknown_grants = policy_grants - set(CAPABILITY_PERMISSIONS)
        if unknown_grants:
            raise PermissionDeniedError(f"Unknown policy grant '{sorted(unknown_grants)[0]}'.")
        decision = resolve_permissions(descriptor.permissions, policy_grants)
        return PluginPermissionReport(
            descriptor.identity,
            tuple(sorted(descriptor.permissions)),
            tuple(sorted(decision.granted)),
            tuple(sorted(decision.denied)),
        )


@dataclass(frozen=True)
class PluginDiscoveryService:
    file_loader: Callable[[list[Path]], dict[str, ProviderDescriptor]] | None = None
    directory_loader: Callable[[Path], dict[str, ProviderDescriptor]] | None = None

    def discover(
        self, manifests: list[tuple[Mapping[str, object], str]]
    ) -> dict[str, ProviderDescriptor]:
        return register_descriptors(manifests)

    def discover_files(self, locations: list[Path]) -> dict[str, ProviderDescriptor]:
        """Validate manifest files through the injected safe loader."""

        if self.file_loader is None:
            raise PluginManifestError("Plugin manifest file discovery is not configured.")
        return self.file_loader(locations)

    def discover_directory(self, location: Path) -> dict[str, ProviderDescriptor]:
        """Discover and validate manifests in one configured directory."""

        if self.directory_loader is None:
            raise PluginManifestError("Plugin manifest directory discovery is not configured.")
        return self.directory_loader(location)

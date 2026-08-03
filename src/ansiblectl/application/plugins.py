"""Plugin discovery use case."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from ansiblectl.domain.plugins import PluginManifestError, ProviderDescriptor, register_descriptors


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

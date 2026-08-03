"""Plugin discovery use case."""

from collections.abc import Mapping
from dataclasses import dataclass

from ansiblectl.domain.plugins import ProviderDescriptor, register_descriptors


@dataclass(frozen=True)
class PluginDiscoveryService:
    def discover(
        self, manifests: list[tuple[Mapping[str, object], str]]
    ) -> dict[str, ProviderDescriptor]:
        return register_descriptors(manifests)

"""Safe YAML manifest discovery before plugin code loading."""

from collections.abc import Mapping
from pathlib import Path

import yaml

from ansiblectl.domain.plugins import PluginManifestError, ProviderDescriptor, register_descriptors


def discover_manifests(locations: list[Path]) -> dict[str, ProviderDescriptor]:
    manifests: list[tuple[Mapping[str, object], str]] = []
    for location in locations:
        try:
            data = yaml.safe_load(location.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as error:
            raise PluginManifestError(f"Manifest at {location} cannot be parsed safely.") from error
        if not isinstance(data, dict):
            raise PluginManifestError(f"Manifest at {location} must be a YAML mapping.")
        manifests.append((data, str(location)))
    return register_descriptors(manifests)

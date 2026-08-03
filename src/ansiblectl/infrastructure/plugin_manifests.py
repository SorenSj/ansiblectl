"""Safe YAML manifest discovery before plugin code loading."""

from collections.abc import Mapping
from pathlib import Path

import yaml

from ansiblectl.domain.plugins import PluginManifestError, ProviderDescriptor, register_descriptors


def discover_manifest_directory(location: Path) -> dict[str, ProviderDescriptor]:
    """Discover direct YAML manifest children deterministically without following symlinks."""

    if location.is_symlink():
        raise PluginManifestError(
            f"Plugin manifest directory at {location} must not be a symbolic link."
        )
    if not location.is_dir():
        raise PluginManifestError(f"Plugin manifest directory at {location} does not exist.")
    manifests: list[Path] = []
    try:
        children = sorted(location.iterdir(), key=lambda path: path.name)
    except OSError as error:
        raise PluginManifestError(
            f"Plugin manifest directory at {location} cannot be read safely."
        ) from error
    for child in children:
        if child.suffix.lower() not in {".yaml", ".yml"}:
            continue
        if child.is_symlink():
            raise PluginManifestError(f"Manifest at {child} must not be a symbolic link.")
        if child.is_file():
            manifests.append(child)
    return discover_manifests(manifests)


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

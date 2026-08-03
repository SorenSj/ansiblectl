"""Validated plugin manifest types and deterministic descriptor registry."""

from collections.abc import Mapping
from dataclasses import dataclass

from ansiblectl.domain.errors import ErrorCode, PluginError

SDK_VERSION = "0.1"


class PluginManifestError(PluginError):
    """Raised for safe source-aware manifest diagnostics."""

    error_code = ErrorCode.PLUGIN_MANIFEST_INVALID


@dataclass(frozen=True)
class ProviderDescriptor:
    identity: str
    version: str
    sdk_compatibility: str
    capabilities: tuple[str, ...]
    configuration_schema: str
    permissions: tuple[str, ...]
    source: str


def parse_manifest(values: Mapping[str, object], source: str) -> ProviderDescriptor:
    required = {
        "identity",
        "version",
        "sdk_compatibility",
        "capabilities",
        "configuration_schema",
        "permissions",
    }
    missing = required - set(values)
    if missing:
        raise PluginManifestError(f"Manifest at {source} is missing field '{sorted(missing)[0]}'.")
    identity, version, compatibility, schema = (
        values["identity"],
        values["version"],
        values["sdk_compatibility"],
        values["configuration_schema"],
    )
    if not all(
        isinstance(value, str) and value for value in (identity, version, compatibility, schema)
    ):
        raise PluginManifestError(f"Manifest at {source} has an invalid string field.")
    capabilities, permissions = values["capabilities"], values["permissions"]
    if not all(
        isinstance(value, list) and all(isinstance(item, str) and item for item in value)
        for value in (capabilities, permissions)
    ):
        raise PluginManifestError(f"Manifest at {source} has invalid capabilities or permissions.")
    if compatibility != SDK_VERSION:
        raise PluginManifestError(
            f"Manifest at {source} declares incompatible SDK '{compatibility}'. "
            f"Expected {SDK_VERSION}."
        )
    assert isinstance(identity, str)
    assert isinstance(version, str)
    assert isinstance(schema, str)
    assert isinstance(capabilities, list)
    assert isinstance(permissions, list)
    return ProviderDescriptor(
        identity, version, compatibility, tuple(capabilities), schema, tuple(permissions), source
    )


def register_descriptors(
    manifests: list[tuple[Mapping[str, object], str]],
) -> dict[str, ProviderDescriptor]:
    descriptors = [parse_manifest(values, source) for values, source in manifests]
    registry: dict[str, ProviderDescriptor] = {}
    for descriptor in descriptors:
        if descriptor.identity in registry:
            raise PluginManifestError(
                f"Duplicate provider identity '{descriptor.identity}' from {descriptor.source}."
            )
        registry[descriptor.identity] = descriptor
    return registry

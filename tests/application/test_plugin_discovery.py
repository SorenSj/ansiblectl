"""Plugin discovery use-case tests."""

from pathlib import Path

import pytest

from ansiblectl.application.plugins import PluginDiscoveryService
from ansiblectl.domain.plugins import PluginManifestError, ProviderDescriptor


def test_discovery_returns_validated_descriptors() -> None:
    manifest = {
        "identity": "sample",
        "version": "1.0",
        "sdk_compatibility": "0.1",
        "capabilities": ["provider"],
        "configuration_schema": "schema.json",
        "permissions": [],
    }
    assert "sample" in PluginDiscoveryService().discover([(manifest, "sample.yaml")])


def test_file_discovery_delegates_to_injected_safe_loader(tmp_path: Path) -> None:
    location = tmp_path / "sample.yaml"
    descriptor = ProviderDescriptor("sample", "1.0", "0.1", (), "schema.json", (), str(location))
    captured: list[Path] = []

    def loader(locations: list[Path]) -> dict[str, ProviderDescriptor]:
        captured.extend(locations)
        return {"sample": descriptor}

    assert PluginDiscoveryService(loader).discover_files([location]) == {"sample": descriptor}
    assert captured == [location]


def test_file_discovery_requires_a_configured_loader(tmp_path: Path) -> None:
    with pytest.raises(PluginManifestError, match="not configured"):
        PluginDiscoveryService().discover_files([tmp_path / "sample.yaml"])

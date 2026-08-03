"""Filesystem manifest discovery tests."""

from pathlib import Path

import pytest

from ansiblectl.domain.plugins import PluginManifestError
from ansiblectl.infrastructure.plugin_manifests import discover_manifests


def test_discovery_validates_yaml_before_any_code_load(tmp_path: Path) -> None:
    manifest = tmp_path / "provider.yaml"
    manifest.write_text(
        "identity: demo\n"
        "version: '1.0'\n"
        "sdk_compatibility: '0.1'\n"
        "capabilities: [provider]\n"
        "configuration_schema: schema.json\n"
        "permissions: []\n"
    )
    assert discover_manifests([manifest])["demo"].source == str(manifest)


def test_malformed_file_has_source_aware_diagnostic(tmp_path: Path) -> None:
    manifest = tmp_path / "bad.yaml"
    manifest.write_text("- not-a-mapping\n")
    with pytest.raises(PluginManifestError, match="must be a YAML mapping"):
        discover_manifests([manifest])

"""Filesystem manifest discovery tests."""

from pathlib import Path

import pytest

from ansiblectl.domain.plugins import PluginManifestError
from ansiblectl.infrastructure.plugin_manifests import (
    discover_manifest_directory,
    discover_manifests,
)


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


def test_directory_discovery_loads_direct_yaml_children_in_name_order(tmp_path: Path) -> None:
    for filename, identity in (("b.yaml", "second"), ("a.yml", "first")):
        (tmp_path / filename).write_text(
            f"identity: {identity}\n"
            "version: '1.0'\n"
            "sdk_compatibility: '0.1'\n"
            "capabilities: [provider]\n"
            "configuration_schema: schema.json\n"
            "permissions: []\n",
            encoding="utf-8",
        )
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "nested.yaml").write_text("not inspected", encoding="utf-8")

    descriptors = discover_manifest_directory(tmp_path)

    assert list(descriptors) == ["first", "second"]


def test_directory_discovery_rejects_symlinked_manifest(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("outside-like content", encoding="utf-8")
    (tmp_path / "provider.yaml").symlink_to(target)

    with pytest.raises(PluginManifestError, match="must not be a symbolic link"):
        discover_manifest_directory(tmp_path)


def test_directory_discovery_requires_existing_directory(tmp_path: Path) -> None:
    with pytest.raises(PluginManifestError, match="does not exist"):
        discover_manifest_directory(tmp_path / "missing")

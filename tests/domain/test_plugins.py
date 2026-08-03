"""Plugin manifest validation tests."""

import pytest

from ansiblectl.domain.plugins import PluginManifestError, parse_manifest, register_descriptors


def _manifest(identity: str = "example") -> dict[str, object]:
    return {
        "identity": identity,
        "version": "1.0",
        "sdk_compatibility": "0.1",
        "capabilities": ["provider"],
        "configuration_schema": "schema.json",
        "permissions": ["network"],
    }


def test_manifest_is_validated_before_registration() -> None:
    with pytest.raises(PluginManifestError, match="missing field"):
        parse_manifest({"identity": "bad"}, "plugin.yaml")


def test_incompatible_sdk_and_duplicate_identities_fail_deterministically() -> None:
    incompatible = _manifest()
    incompatible["sdk_compatibility"] = "2.0"
    with pytest.raises(PluginManifestError, match="incompatible SDK"):
        parse_manifest(incompatible, "bad.yaml")
    with pytest.raises(PluginManifestError, match="Duplicate provider identity"):
        register_descriptors([(_manifest(), "one.yaml"), (_manifest(), "two.yaml")])


def test_valid_registry_preserves_source_metadata() -> None:
    registry = register_descriptors([(_manifest(), "plugin.yaml")])
    assert registry["example"].source == "plugin.yaml"

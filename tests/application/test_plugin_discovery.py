"""Plugin discovery use-case tests."""

from ansiblectl.application.plugins import PluginDiscoveryService


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

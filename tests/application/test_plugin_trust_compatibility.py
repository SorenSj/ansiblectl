"""Regression contracts between legacy plugin flows and unattended trust."""

from collections.abc import Mapping
from dataclasses import dataclass, field

import pytest

from ansiblectl.application.plugins import PluginDiscoveryService, PluginPermissionService
from ansiblectl.domain.plugin_policy import evaluate_unattended_policy
from ansiblectl.domain.plugin_trust import PluginProvenance, PluginTrustError, PluginTrustReason
from ansiblectl.plugins.runtime import PluginRuntime
from ansiblectl.sdk.context import SDKContext


@dataclass
class _LegacyPlugin:
    contexts: list[SDKContext] = field(default_factory=list)

    def initialize(self, context: SDKContext) -> tuple[str, ...]:
        self.contexts.append(context)
        return ("provider",)

    def shutdown(self) -> None:
        return None


def test_legacy_manifest_and_interactive_grants_remain_opt_in_and_unchanged() -> None:
    manifests: list[tuple[Mapping[str, object], str]] = [
        (
            {
                "identity": "legacy.provider",
                "version": "1.0",
                "sdk_compatibility": "0.1",
                "capabilities": ["provider"],
                "configuration_schema": "schema.json",
                "permissions": ["network", "secrets"],
            },
            "legacy.yaml",
        )
    ]
    descriptor = PluginDiscoveryService().discover(manifests)["legacy.provider"]

    report = PluginPermissionService().evaluate(descriptor, frozenset({"network"}))
    plugin = _LegacyPlugin()
    runtime = PluginRuntime()

    assert report.granted == ("network",)
    assert report.denied == ("secrets",)
    assert runtime.load(descriptor, plugin, frozenset(report.granted)) is True
    assert plugin.contexts == [SDKContext(frozenset({"network"}))]
    assert runtime.registered_capabilities == {"legacy.provider": ("provider",)}


def test_unattended_default_denial_does_not_change_interactive_preflight() -> None:
    provenance = PluginProvenance(
        provider_identity="legacy.provider",
        plugin_version="1.0",
        sdk_compatibility="0.1",
        artifact_digest=f"sha256:{'a' * 64}",
        origin="local:legacy.provider",
        signing_key_id=f"ed25519:sha256:{'b' * 64}",
        signature=b"s" * 64,
    )

    with pytest.raises(PluginTrustError) as raised:
        evaluate_unattended_policy(provenance, ("network",), None)
    assert raised.value.reason is PluginTrustReason.POLICY_REQUIRED

    descriptor = PluginDiscoveryService().discover(
        [
            (
                {
                    "identity": "legacy.provider",
                    "version": "1.0",
                    "sdk_compatibility": "0.1",
                    "capabilities": [],
                    "configuration_schema": "schema.json",
                    "permissions": ["network"],
                },
                "legacy.yaml",
            )
        ]
    )["legacy.provider"]
    assert PluginPermissionService().evaluate(descriptor, frozenset({"network"})).granted == (
        "network",
    )

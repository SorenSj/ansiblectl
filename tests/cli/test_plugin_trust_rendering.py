"""Redacted human, JSON, and YAML plugin trust decision contracts."""

import json
from dataclasses import replace
from io import StringIO

import pytest
import yaml

from ansiblectl.cli.rendering import render_plugin_trust_decision
from ansiblectl.domain.plugin_trust import (
    PluginProvenance,
    PluginTrustDecision,
    PluginTrustReason,
)

_FORBIDDEN = (
    "raw-signature-secret",
    "raw-public-key-secret",
    "/private/plugins/provider.whl",
    "registry-password",
    "allow: everything",
)


def _provenance() -> PluginProvenance:
    return PluginProvenance(
        provider_identity="example.provider",
        plugin_version="1.2.3",
        sdk_compatibility="0.1",
        artifact_digest=f"sha256:{'a' * 64}",
        origin="https://plugins.example.test/releases",
        signing_key_id=f"ed25519:sha256:{'b' * 64}",
        signature=b"raw-signature-secret",
    )


@pytest.mark.parametrize("reason", list(PluginTrustReason))
@pytest.mark.parametrize("output_format", ["text", "json", "yaml"])
def test_every_stable_reason_has_same_redacted_public_contract(
    reason: PluginTrustReason, output_format: str
) -> None:
    decision = PluginTrustDecision.denied(_provenance(), ("secrets", "network"), reason)
    output = StringIO()

    render_plugin_trust_decision(decision, output_format, output)

    rendered = output.getvalue()
    assert reason.value in rendered
    assert all(secret not in rendered for secret in _FORBIDDEN)
    if output_format == "text":
        assert "Plugin trust: denied" in rendered
        assert "Granted permissions: none" in rendered
    else:
        payload = json.loads(rendered) if output_format == "json" else yaml.safe_load(rendered)
        assert payload == decision.to_payload()
        assert payload["trusted"] is False
        assert payload["reasons"] == [reason.value]


@pytest.mark.parametrize("output_format", ["text", "json", "yaml"])
def test_trusted_decision_reports_exact_grants_without_a_failure_reason(
    output_format: str,
) -> None:
    decision = PluginTrustDecision.allowed(_provenance(), ("network", "network"))
    output = StringIO()

    render_plugin_trust_decision(decision, output_format, output)

    rendered = output.getvalue()
    assert all(secret not in rendered for secret in _FORBIDDEN)
    assert decision.granted_permissions == ("network",)
    assert decision.denied_permissions == ()
    assert decision.reasons == ()


def test_decision_rejects_raw_key_material_before_public_rendering() -> None:
    decision = PluginTrustDecision.allowed(_provenance(), ())

    with pytest.raises(ValueError, match="public canonical schema"):
        replace(decision, signing_key_id="raw-public-key-secret")

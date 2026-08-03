"""Unattended plugin policy contract tests."""

import pytest

from ansiblectl.domain.plugin_policy import (
    PluginPolicyRule,
    UnattendedPluginPolicy,
    evaluate_unattended_policy,
)
from ansiblectl.domain.plugin_trust import PluginProvenance, PluginTrustError, PluginTrustReason


def _provenance() -> PluginProvenance:
    return PluginProvenance(
        provider_identity="example.provider",
        plugin_version="1.2.3",
        sdk_compatibility="0.1",
        artifact_digest=f"sha256:{'a' * 64}",
        origin="https://plugins.example.test/releases",
        signing_key_id=f"ed25519:sha256:{'b' * 64}",
        signature=b"s" * 64,
    )


def _rule(
    *,
    provider_identity: str = "example.provider",
    permissions: frozenset[str] = frozenset({"network", "secrets"}),
    plugin_version: str | None = "1.2.3",
) -> PluginPolicyRule:
    return PluginPolicyRule(
        provider_identity=provider_identity,
        permissions=permissions,
        plugin_version=plugin_version,
        artifact_digest=f"sha256:{'a' * 64}",
        signing_key_id=f"ed25519:sha256:{'b' * 64}",
        origins=frozenset({"https://plugins.example.test/releases"}),
    )


def _reason(policy: UnattendedPluginPolicy | None, requested: tuple[str, ...] = ()) -> str:
    with pytest.raises(PluginTrustError) as raised:
        evaluate_unattended_policy(_provenance(), requested, policy)
    reason = raised.value.context["reason"]
    assert isinstance(reason, str)
    return reason


def test_exact_allow_grants_only_requested_permissions() -> None:
    policy = UnattendedPluginPolicy(allow=(_rule(),))

    assert evaluate_unattended_policy(_provenance(), ("network",), policy) == frozenset({"network"})


def test_missing_or_unsupported_policy_is_required() -> None:
    assert _reason(None) == PluginTrustReason.POLICY_REQUIRED
    assert _reason(UnattendedPluginPolicy(allow=(), schema_version=2)) == (
        PluginTrustReason.POLICY_REQUIRED
    )


def test_deny_overrides_allow_independent_of_rule_order() -> None:
    allow = _rule()
    unrelated = _rule(provider_identity="other.provider", permissions=frozenset())
    deny = _rule(permissions=frozenset({"network"}))

    for denies in ((unrelated, deny), (deny, unrelated)):
        policy = UnattendedPluginPolicy(allow=(allow,), deny=denies)
        assert _reason(policy, ("network",)) == PluginTrustReason.POLICY_DENIED


def test_empty_deny_permission_set_denies_entire_matching_plugin() -> None:
    policy = UnattendedPluginPolicy(allow=(_rule(),), deny=(_rule(permissions=frozenset()),))

    assert _reason(policy) == PluginTrustReason.POLICY_DENIED


def test_no_allow_and_multiple_allows_have_distinct_stable_reasons() -> None:
    assert _reason(UnattendedPluginPolicy(allow=())) == PluginTrustReason.POLICY_DENIED
    assert _reason(UnattendedPluginPolicy(allow=(_rule(), _rule()))) == (
        PluginTrustReason.POLICY_AMBIGUOUS
    )


@pytest.mark.parametrize(
    "requested",
    [("secrets",), ("subprocess",)],
)
def test_permission_ceiling_rejects_missing_and_unknown_authority(
    requested: tuple[str, ...],
) -> None:
    policy = UnattendedPluginPolicy(allow=(_rule(permissions=frozenset({"network"})),))

    assert _reason(policy, requested) == PluginTrustReason.PERMISSION_CEILING_EXCEEDED


def test_local_restrictions_can_remove_but_never_add_authority() -> None:
    policy = UnattendedPluginPolicy(
        allow=(_rule(permissions=frozenset({"network"})),),
        local_restrictions=(_rule(permissions=frozenset()),),
    )

    assert _reason(policy, ("network",)) == PluginTrustReason.PERMISSION_CEILING_EXCEEDED
    assert evaluate_unattended_policy(_provenance(), (), policy) == frozenset()


def test_nonmatching_exact_constraint_cannot_authorize_plugin() -> None:
    policy = UnattendedPluginPolicy(allow=(_rule(plugin_version="9.9.9"),))

    assert _reason(policy) == PluginTrustReason.POLICY_DENIED

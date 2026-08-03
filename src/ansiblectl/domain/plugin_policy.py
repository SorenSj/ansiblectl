"""Pure, deterministic unattended policy evaluation for trusted plugins."""

from __future__ import annotations

from dataclasses import dataclass

from ansiblectl.domain.permissions import CAPABILITY_PERMISSIONS
from ansiblectl.domain.plugin_trust import (
    PluginProvenance,
    PluginTrustError,
    PluginTrustReason,
)


@dataclass(frozen=True)
class PluginPolicyRule:
    """One identity-pinned rule with optional exact provenance constraints."""

    provider_identity: str
    permissions: frozenset[str] = frozenset()
    plugin_version: str | None = None
    artifact_digest: str | None = None
    signing_key_id: str | None = None
    origins: frozenset[str] | None = None

    def matches(self, provenance: PluginProvenance) -> bool:
        """Match only explicit signed fields; no external state participates."""

        return (
            self.provider_identity == provenance.provider_identity
            and (self.plugin_version is None or self.plugin_version == provenance.plugin_version)
            and (self.artifact_digest is None or self.artifact_digest == provenance.artifact_digest)
            and (self.signing_key_id is None or self.signing_key_id == provenance.signing_key_id)
            and (self.origins is None or provenance.origin in self.origins)
        )


@dataclass(frozen=True)
class UnattendedPluginPolicy:
    """Versioned managed policy plus optional authority-reducing restrictions."""

    allow: tuple[PluginPolicyRule, ...]
    deny: tuple[PluginPolicyRule, ...] = ()
    local_restrictions: tuple[PluginPolicyRule, ...] = ()
    schema_version: int = 1


def evaluate_unattended_policy(
    provenance: PluginProvenance,
    requested_permissions: tuple[str, ...],
    policy: UnattendedPluginPolicy | None,
) -> frozenset[str]:
    """Return the exact unattended grants or fail with one stable reason."""

    if policy is None or policy.schema_version != 1:
        raise PluginTrustError(PluginTrustReason.POLICY_REQUIRED)
    requested = frozenset(requested_permissions)
    known_permissions = frozenset(CAPABILITY_PERMISSIONS)
    if not requested <= known_permissions or any(
        not rule.permissions <= known_permissions
        for rule in (*policy.deny, *policy.allow, *policy.local_restrictions)
    ):
        raise PluginTrustError(PluginTrustReason.PERMISSION_CEILING_EXCEEDED)
    matching_denies = tuple(rule for rule in policy.deny if rule.matches(provenance))
    if any(not rule.permissions or requested & rule.permissions for rule in matching_denies):
        raise PluginTrustError(PluginTrustReason.POLICY_DENIED)
    matching_allows = tuple(rule for rule in policy.allow if rule.matches(provenance))
    if not matching_allows:
        raise PluginTrustError(PluginTrustReason.POLICY_DENIED)
    if len(matching_allows) != 1:
        raise PluginTrustError(PluginTrustReason.POLICY_AMBIGUOUS)
    granted = matching_allows[0].permissions
    if not requested <= granted:
        raise PluginTrustError(PluginTrustReason.PERMISSION_CEILING_EXCEEDED)
    for restriction in policy.local_restrictions:
        if restriction.matches(provenance) and not requested <= restriction.permissions:
            raise PluginTrustError(PluginTrustReason.PERMISSION_CEILING_EXCEEDED)
    return requested


__all__ = ["PluginPolicyRule", "UnattendedPluginPolicy", "evaluate_unattended_policy"]

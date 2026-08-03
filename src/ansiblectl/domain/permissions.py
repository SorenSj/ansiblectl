"""Default-deny permission resolution for plugin capabilities."""

from dataclasses import dataclass

from ansiblectl.domain.errors import DomainError


class PermissionDeniedError(DomainError):
    """Raised before privileged plugin work can start."""


CAPABILITY_PERMISSIONS = {
    "network": "network",
    "secrets": "secrets",
    "filesystem_write": "filesystem_write",
}


@dataclass(frozen=True)
class PermissionDecision:
    granted: frozenset[str]
    denied: frozenset[str]


def resolve_permissions(
    requested: tuple[str, ...], policy_grants: frozenset[str]
) -> PermissionDecision:
    unknown = set(requested) - set(CAPABILITY_PERMISSIONS)
    if unknown:
        raise PermissionDeniedError(f"Unknown requested permission '{sorted(unknown)[0]}'.")
    granted = frozenset(permission for permission in requested if permission in policy_grants)
    return PermissionDecision(granted, frozenset(requested) - granted)


def require_permission(decision: PermissionDecision, permission: str) -> None:
    if permission not in decision.granted:
        raise PermissionDeniedError(
            f"Permission '{permission}' was denied by policy before privileged work started."
        )

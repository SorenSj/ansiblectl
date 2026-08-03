"""Permission-policy tests."""

import pytest

from ansiblectl.domain.permissions import (
    PermissionDeniedError,
    require_permission,
    resolve_permissions,
)


def test_default_deny_and_explicit_grant_are_deterministic() -> None:
    denied = resolve_permissions(("secrets",), frozenset())
    assert denied.granted == frozenset()
    with pytest.raises(PermissionDeniedError, match="before privileged work"):
        require_permission(denied, "secrets")
    assert resolve_permissions(("network",), frozenset({"network"})).granted == frozenset(
        {"network"}
    )

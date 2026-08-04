"""Exact secret-provider routing contract tests."""

from dataclasses import dataclass, field

import pytest

from ansiblectl.domain.secrets import (
    SecretMaterial,
    SecretNotFoundError,
    SecretReference,
)
from ansiblectl.infrastructure.secret_router import SecretProviderRouter


@dataclass
class Provider:
    value: str = "sentinel-material"
    calls: list[SecretReference] = field(default_factory=list)

    def resolve(self, reference: SecretReference) -> SecretMaterial:
        self.calls.append(reference)
        return SecretMaterial(self.value)


def test_router_dispatches_to_exact_selected_provider_once() -> None:
    environment = Provider()
    workspace_file = Provider()
    router = SecretProviderRouter({"env": environment, "file": workspace_file})
    reference = SecretReference("file", "WEBHOOK_KEY")

    material = router.resolve(reference)

    assert material.reveal_for_operation() == "sentinel-material"
    assert workspace_file.calls == [reference]
    assert environment.calls == []
    assert "sentinel-material" not in repr(router)


def test_router_rejects_unknown_provider_without_fallback() -> None:
    environment = Provider()
    reference = SecretReference("vault", "WEBHOOK_KEY")

    with pytest.raises(SecretNotFoundError) as caught:
        SecretProviderRouter({"env": environment}).resolve(reference)

    assert str(caught.value) == "Secret material is unavailable from the selected provider."
    assert environment.calls == []
    assert reference.provider not in str(caught.value)
    assert reference.key not in str(caught.value)

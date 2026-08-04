"""Exact secret-provider routing without fallback."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from ansiblectl.domain.secrets import (
    SecretMaterial,
    SecretNotFoundError,
    SecretProvider,
    SecretReference,
)

_UNAVAILABLE_MESSAGE = "Secret material is unavailable from the selected provider."


@dataclass(frozen=True)
class SecretProviderRouter:
    """Dispatch a reference to exactly one explicitly configured provider."""

    providers: Mapping[str, SecretProvider] = field(repr=False)

    def resolve(self, reference: SecretReference) -> SecretMaterial:
        provider = self.providers.get(reference.provider)
        if provider is None:
            raise SecretNotFoundError(_UNAVAILABLE_MESSAGE)
        return provider.resolve(reference)


__all__ = ["SecretProviderRouter"]

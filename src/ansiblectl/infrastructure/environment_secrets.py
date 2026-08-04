"""Exact, non-enumerating process-environment secret resolution."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from ansiblectl.domain.secrets import SecretMaterial, SecretNotFoundError, SecretReference

_ENVIRONMENT_SECRET_KEY = re.compile(r"[A-Z][A-Z0-9_]{0,127}", re.ASCII)
_UNAVAILABLE_MESSAGE = "Secret material is unavailable from the selected provider."


@dataclass(frozen=True)
class EnvironmentSecretProvider:
    """Resolve one canonical ``env`` reference without inspecting unrelated keys."""

    environment: Mapping[str, str] = field(repr=False)

    def resolve(self, reference: SecretReference) -> SecretMaterial:
        if reference.provider != "env" or _ENVIRONMENT_SECRET_KEY.fullmatch(reference.key) is None:
            raise SecretNotFoundError(_UNAVAILABLE_MESSAGE)
        try:
            value = self.environment[reference.key]
        except Exception as error:
            raise SecretNotFoundError(_UNAVAILABLE_MESSAGE) from error
        if not isinstance(value, str) or not value or any(_is_control(char) for char in value):
            raise SecretNotFoundError(_UNAVAILABLE_MESSAGE)
        return SecretMaterial(value)


def _is_control(character: str) -> bool:
    codepoint = ord(character)
    return codepoint <= 31 or 127 <= codepoint <= 159


__all__ = ["EnvironmentSecretProvider"]

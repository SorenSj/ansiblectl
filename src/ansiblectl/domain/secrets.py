"""Secret provider contracts that keep material out of ordinary data models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ansiblectl.domain.errors import ErrorCode, SecretsError


class SecretError(SecretsError):
    """Base class for provider-aware secret retrieval failures."""


class SecretNotFoundError(SecretError):
    """Raised when a provider cannot resolve a requested key."""

    error_code = ErrorCode.SECRET_NOT_FOUND


@dataclass(frozen=True)
class SecretReference:
    provider: str
    key: str

    def __post_init__(self) -> None:
        if (
            not self.provider
            or not self.key
            or any(char.isspace() for char in self.provider + self.key)
        ):
            raise SecretError(
                "Secret reference must contain a provider and key without whitespace."
            )

    def __str__(self) -> str:
        return f"{self.provider}:{self.key}"


class SecretMaterial:
    """In-memory material deliberately excluded from repr, logs, and payloads."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal_for_operation(self) -> str:
        """Return material only at the immediate privileged operation boundary."""

        return self._value

    def __repr__(self) -> str:
        return "SecretMaterial(<redacted>)"


@dataclass(frozen=True)
class SecretAuditRecord:
    reference: SecretReference
    outcome: str


class SecretProvider(Protocol):
    def resolve(self, reference: SecretReference) -> SecretMaterial:
        """Resolve material in memory or raise a typed provider-aware error."""

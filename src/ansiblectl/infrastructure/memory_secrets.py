"""Test-oriented in-memory secret provider; production backends remain external adapters."""

from dataclasses import dataclass

from ansiblectl.domain.secrets import SecretMaterial, SecretNotFoundError, SecretReference


@dataclass(frozen=True)
class MemorySecretProvider:
    provider_name: str
    values: dict[str, str]

    def resolve(self, reference: SecretReference) -> SecretMaterial:
        if reference.provider != self.provider_name or reference.key not in self.values:
            raise SecretNotFoundError(
                f"Secret '{reference}' was not found. Verify provider access and the requested key."
            )
        return SecretMaterial(self.values[reference.key])

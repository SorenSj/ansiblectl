"""Secret resolution use case with safe audit metadata."""

from dataclasses import dataclass

from ansiblectl.domain.secrets import (
    SecretAuditRecord,
    SecretMaterial,
    SecretProvider,
    SecretReference,
)


@dataclass(frozen=True)
class SecretService:
    provider: SecretProvider

    def resolve(self, reference: SecretReference) -> tuple[SecretMaterial, SecretAuditRecord]:
        material = self.provider.resolve(reference)
        return material, SecretAuditRecord(reference, "resolved")

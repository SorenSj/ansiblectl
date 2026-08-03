"""Secret use-case tests with an explicit fake provider."""

from ansiblectl.application.secrets import SecretService
from ansiblectl.domain.secrets import SecretMaterial, SecretReference


class FakeProvider:
    def resolve(self, reference: SecretReference) -> SecretMaterial:
        return SecretMaterial("test-value")


def test_fake_provider_returns_material_and_safe_audit_record() -> None:
    material, audit = SecretService(FakeProvider()).resolve(SecretReference("fake", "token"))

    assert material.reveal_for_operation() == "test-value"
    assert str(audit.reference) == "fake:token"
    assert "test-value" not in repr(audit)

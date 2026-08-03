"""Secret boundary tests."""

import pytest

from ansiblectl.domain.secrets import SecretError, SecretMaterial, SecretReference


def test_reference_never_embeds_value_and_material_repr_is_redacted() -> None:
    reference = SecretReference("env", "DEPLOY_TOKEN")
    material = SecretMaterial("very-secret")

    assert str(reference) == "env:DEPLOY_TOKEN"
    assert "very-secret" not in repr(material)


def test_malformed_reference_fails_safely() -> None:
    with pytest.raises(SecretError, match="provider and key"):
        SecretReference("env", "bad key")

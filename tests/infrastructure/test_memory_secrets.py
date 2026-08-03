"""Memory provider tests."""

import pytest

from ansiblectl.domain.secrets import SecretNotFoundError, SecretReference
from ansiblectl.infrastructure.memory_secrets import MemorySecretProvider


def test_missing_secret_has_provider_aware_remediation() -> None:
    with pytest.raises(SecretNotFoundError, match="Verify provider access"):
        MemorySecretProvider("env", {}).resolve(SecretReference("env", "TOKEN"))

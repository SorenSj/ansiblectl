"""Production environment secret provider contract tests."""

from collections.abc import Iterator, Mapping

import pytest

from ansiblectl.domain.secrets import SecretNotFoundError, SecretReference
from ansiblectl.infrastructure.environment_secrets import EnvironmentSecretProvider


class TrackedEnvironment(Mapping[str, str]):
    def __init__(self, values: dict[str, str], failure: Exception | None = None) -> None:
        self._values = values
        self.failure = failure
        self.lookups: list[str] = []
        self.enumerated = False

    def __getitem__(self, key: str) -> str:
        self.lookups.append(key)
        if self.failure is not None:
            raise self.failure
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        self.enumerated = True
        return iter(self._values)

    def __len__(self) -> int:
        self.enumerated = True
        return len(self._values)


@pytest.mark.parametrize("key", ["A", "WEBHOOK_TOKEN", "A1_" + "X" * 125])
def test_provider_resolves_one_exact_canonical_key_without_enumeration(key: str) -> None:
    environment = TrackedEnvironment({key: "sentinel-secret-value", "UNRELATED": "ignored"})

    material = EnvironmentSecretProvider(environment).resolve(SecretReference("env", key))

    assert material.reveal_for_operation() == "sentinel-secret-value"
    assert environment.lookups == [key]
    assert environment.enumerated is False
    assert "sentinel-secret-value" not in repr(material)
    assert "sentinel-secret-value" not in repr(EnvironmentSecretProvider(environment))


@pytest.mark.parametrize(
    "provider,key",
    [
        ("vault", "WEBHOOK_TOKEN"),
        ("env", "lowercase"),
        ("env", "1TOKEN"),
        ("env", "TOKEN-NAME"),
        ("env", "TOKEN.NAME"),
        ("env", "Æ_TOKEN"),
        ("env", "A" * 129),
    ],
)
def test_invalid_reference_fails_before_environment_access(provider: str, key: str) -> None:
    environment = TrackedEnvironment({})

    with pytest.raises(SecretNotFoundError) as caught:
        EnvironmentSecretProvider(environment).resolve(SecretReference(provider, key))

    assert environment.lookups == []
    assert environment.enumerated is False
    assert key not in str(caught.value)


@pytest.mark.parametrize(
    "value", ["", "line\nfeed", "carriage\rreturn", "nul\x00", "del\x7f", "c1\x85"]
)
def test_missing_or_control_bearing_material_has_one_redacted_failure(value: str) -> None:
    key = "SENTINEL_SECRET_KEY"
    environment = TrackedEnvironment({key: value})

    with pytest.raises(SecretNotFoundError) as caught:
        EnvironmentSecretProvider(environment).resolve(SecretReference("env", key))

    assert str(caught.value) == "Secret material is unavailable from the selected provider."
    assert key not in str(caught.value)
    if value:
        assert value not in str(caught.value)
    assert environment.lookups == [key]


def test_absent_or_exceptional_lookup_is_redacted_and_not_retried() -> None:
    key = "SENTINEL_SECRET_KEY"
    for environment in (
        TrackedEnvironment({}),
        TrackedEnvironment({}, RuntimeError("sentinel underlying detail")),
    ):
        with pytest.raises(SecretNotFoundError) as caught:
            EnvironmentSecretProvider(environment).resolve(SecretReference("env", key))

        assert str(caught.value) == "Secret material is unavailable from the selected provider."
        assert key not in str(caught.value)
        assert "underlying" not in str(caught.value)
        assert environment.lookups == [key]
        assert environment.enumerated is False

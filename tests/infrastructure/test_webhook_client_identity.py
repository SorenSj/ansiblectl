"""Mutual TLS client identity material validation tests."""

from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from ansiblectl.domain.errors import ConfigurationError
from ansiblectl.domain.secrets import SecretMaterial
from ansiblectl.infrastructure.webhook_client_identity import (
    MAX_WEBHOOK_CLIENT_CERTIFICATE_BYTES,
    MAX_WEBHOOK_CLIENT_CERTIFICATES,
    MAX_WEBHOOK_CLIENT_PRIVATE_KEY_BYTES,
    validate_webhook_client_identity,
)


def identity_material(
    *,
    key: rsa.RSAPrivateKey | None = None,
    usages: list[x509.ObjectIdentifier] | None = None,
) -> tuple[bytes, bytes]:
    private_key = key or rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-client")])
    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
    )
    if usages is not None:
        builder = builder.add_extension(x509.ExtendedKeyUsage(usages), critical=False)
    certificate = builder.sign(private_key, hashes.SHA256())
    return (
        certificate.public_bytes(serialization.Encoding.PEM),
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )


def test_validator_returns_only_one_redacted_canonical_transport_identity() -> None:
    certificate, private_key = identity_material(usages=[ExtendedKeyUsageOID.CLIENT_AUTH])

    identity = validate_webhook_client_identity(
        SecretMaterial(certificate.decode("ascii")), SecretMaterial(private_key.decode("ascii"))
    )

    assert identity.reveal_for_transport() == (certificate, private_key)
    assert repr(identity) == "WebhookClientIdentity(<redacted>)"
    assert "test-client" not in repr(identity)


def test_validator_accepts_a_bounded_ordered_certificate_chain() -> None:
    certificate, private_key = identity_material()
    chain = certificate * MAX_WEBHOOK_CLIENT_CERTIFICATES

    identity = validate_webhook_client_identity(
        SecretMaterial(chain.decode("ascii")), SecretMaterial(private_key.decode("ascii"))
    )

    assert identity.reveal_for_transport()[0] == chain


@pytest.mark.parametrize(
    "certificate_transform",
    [
        lambda value: "",
        lambda value: "not-pem\n",
        lambda value: value + "trailing-data",
        lambda value: value.replace("CERTIFICATE", "PRIVATE KEY"),
        lambda value: value * (MAX_WEBHOOK_CLIENT_CERTIFICATES + 1),
        lambda value: "é" + value,
        lambda value: value + "x" * MAX_WEBHOOK_CLIENT_CERTIFICATE_BYTES,
    ],
)
def test_validator_rejects_invalid_or_excessive_certificate_material(
    certificate_transform: object,
) -> None:
    certificate, private_key = identity_material()
    transformed = certificate_transform(certificate.decode("ascii"))  # type: ignore[operator]

    with pytest.raises(ConfigurationError, match="certificate"):
        validate_webhook_client_identity(
            SecretMaterial(transformed), SecretMaterial(private_key.decode("ascii"))
        )


def test_validator_rejects_mismatch_and_non_client_extended_usage() -> None:
    certificate, _ = identity_material(usages=[ExtendedKeyUsageOID.SERVER_AUTH])
    _, other_key = identity_material()
    with pytest.raises(ConfigurationError, match="do not match"):
        validate_webhook_client_identity(
            SecretMaterial(certificate.decode("ascii")), SecretMaterial(other_key.decode("ascii"))
        )
    matching_certificate, matching_key = identity_material(usages=[ExtendedKeyUsageOID.SERVER_AUTH])
    with pytest.raises(ConfigurationError, match="usage"):
        validate_webhook_client_identity(
            SecretMaterial(matching_certificate.decode("ascii")),
            SecretMaterial(matching_key.decode("ascii")),
        )


@pytest.mark.parametrize("mutation", ["encrypted", "junk", "unicode", "oversize", "empty"])
def test_validator_rejects_unsupported_or_malformed_private_keys(mutation: str) -> None:
    certificate, private_key = identity_material()
    value = private_key.decode("ascii")
    if mutation == "encrypted":
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        value = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(b"sentinel-passphrase"),
        ).decode("ascii")
    elif mutation == "junk":
        value += "trailing-data"
    elif mutation == "unicode":
        value = "é" + value
    elif mutation == "oversize":
        value += "x" * MAX_WEBHOOK_CLIENT_PRIVATE_KEY_BYTES
    else:
        value = ""
    with pytest.raises(ConfigurationError, match="private key"):
        validate_webhook_client_identity(
            SecretMaterial(certificate.decode("ascii")), SecretMaterial(value)
        )

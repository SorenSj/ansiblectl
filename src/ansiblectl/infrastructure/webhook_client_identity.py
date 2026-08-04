"""In-memory validation for outbound webhook mutual TLS identity material."""

from __future__ import annotations

import re

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import ExtendedKeyUsageOID

from ansiblectl.domain.errors import ConfigurationError
from ansiblectl.domain.secrets import SecretMaterial

MAX_WEBHOOK_CLIENT_CERTIFICATE_BYTES = 65_536
MAX_WEBHOOK_CLIENT_PRIVATE_KEY_BYTES = 32_768
MAX_WEBHOOK_CLIENT_CERTIFICATES = 8
_PRIVATE_KEY_PEM = re.compile(
    rb"-----BEGIN (?:PRIVATE KEY|RSA PRIVATE KEY|EC PRIVATE KEY)-----\n"
    rb"(?:[A-Za-z0-9+/]{1,64}\n)*[A-Za-z0-9+/]{1,64}={0,2}\n"
    rb"-----END (?:PRIVATE KEY|RSA PRIVATE KEY|EC PRIVATE KEY)-----\n?"
)


class WebhookClientIdentity:
    """Opaque canonical client identity exposed only at the transport boundary."""

    __slots__ = ("_certificate_chain", "_private_key")

    def __init__(self, certificate_chain: bytes, private_key: bytes) -> None:
        self._certificate_chain = certificate_chain
        self._private_key = private_key

    def reveal_for_transport(self) -> tuple[bytes, bytes]:
        """Return canonical PEM only to the immediate privileged TLS boundary."""

        return self._certificate_chain, self._private_key

    def __repr__(self) -> str:
        return "WebhookClientIdentity(<redacted>)"


def validate_webhook_client_identity(
    certificate_material: SecretMaterial,
    private_key_material: SecretMaterial,
) -> WebhookClientIdentity:
    """Parse, pair, and canonicalize one bounded client certificate identity."""

    certificate_pem = _bounded_ascii(
        certificate_material,
        MAX_WEBHOOK_CLIENT_CERTIFICATE_BYTES,
        "certificate",
    )
    private_key_pem = _bounded_ascii(
        private_key_material,
        MAX_WEBHOOK_CLIENT_PRIVATE_KEY_BYTES,
        "private key",
    )
    try:
        certificates = x509.load_pem_x509_certificates(certificate_pem)
    except ValueError as error:
        raise ConfigurationError("Webhook client identity certificate is invalid.") from error
    if not 1 <= len(certificates) <= MAX_WEBHOOK_CLIENT_CERTIFICATES:
        raise ConfigurationError("Webhook client identity certificate chain is invalid.")
    canonical_chain = b"".join(
        certificate.public_bytes(serialization.Encoding.PEM) for certificate in certificates
    )
    if certificate_pem.strip() + b"\n" != canonical_chain:
        raise ConfigurationError("Webhook client identity certificate encoding is invalid.")
    if _PRIVATE_KEY_PEM.fullmatch(private_key_pem) is None:
        raise ConfigurationError("Webhook client identity private key encoding is invalid.")
    try:
        private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    except (TypeError, ValueError) as error:
        raise ConfigurationError("Webhook client identity private key is invalid.") from error
    public_format = serialization.PublicFormat.SubjectPublicKeyInfo
    leaf_public_key = (
        certificates[0].public_key().public_bytes(serialization.Encoding.DER, public_format)
    )
    private_public_key = private_key.public_key().public_bytes(
        serialization.Encoding.DER, public_format
    )
    if leaf_public_key != private_public_key:
        raise ConfigurationError("Webhook client identity certificate and key do not match.")
    try:
        usages = certificates[0].extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    except x509.ExtensionNotFound:
        pass
    else:
        if ExtendedKeyUsageOID.CLIENT_AUTH not in usages:
            raise ConfigurationError("Webhook client identity certificate usage is invalid.")
    canonical_key = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return WebhookClientIdentity(canonical_chain, canonical_key)


def _bounded_ascii(material: SecretMaterial, limit: int, kind: str) -> bytes:
    try:
        encoded = material.reveal_for_operation().encode("ascii")
    except UnicodeEncodeError as error:
        raise ConfigurationError(f"Webhook client identity {kind} is invalid.") from error
    if not encoded or len(encoded) > limit or b"\r" in encoded or b"\x00" in encoded:
        raise ConfigurationError(f"Webhook client identity {kind} is invalid.")
    return encoded


__all__ = [
    "MAX_WEBHOOK_CLIENT_CERTIFICATE_BYTES",
    "MAX_WEBHOOK_CLIENT_CERTIFICATES",
    "MAX_WEBHOOK_CLIENT_PRIVATE_KEY_BYTES",
    "WebhookClientIdentity",
    "validate_webhook_client_identity",
]

"""Safe exclusive webhook CA bundle loading tests."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.x509.oid import NameOID

from ansiblectl.domain.errors import ConfigurationError
from ansiblectl.infrastructure.webhook_tls_trust_configuration import (
    MAX_WEBHOOK_CA_BUNDLE_BYTES,
    load_webhook_tls_trust_policies,
)

NOW = datetime(2026, 8, 4, tzinfo=UTC)


def certificate(*, ca: bool = True, key_cert_sign: bool = True, expired: bool = False) -> bytes:
    key = ed25519.Ed25519PrivateKey.generate()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-only-ca")])
    start = NOW - timedelta(days=10)
    end = NOW - timedelta(days=1) if expired else NOW + timedelta(days=10)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(end)
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(False, False, False, False, False, key_cert_sign, ca, False, False),
            critical=True,
        )
        .sign(key, None)
    )
    return cert.public_bytes(serialization.Encoding.PEM)


def workspace_policy(tmp_path: Path, bundle: bytes) -> Path:
    private = tmp_path / ".ansiblectl"
    trust = private / "trust/internal"
    trust.mkdir(parents=True)
    (private / "webhook-tls-trust.yaml").write_text(
        "schema_version: 1\npolicies:\n  internal-ca:\n    ca_bundle: internal/root.pem\n",
        encoding="utf-8",
    )
    path = trust / "root.pem"
    path.write_bytes(bundle)
    path.chmod(0o600)
    return path


def test_loader_captures_one_immutable_redacted_ca_snapshot(tmp_path: Path) -> None:
    pem = certificate()
    path = workspace_policy(tmp_path, pem)

    policy = load_webhook_tls_trust_policies(tmp_path, now=NOW)["internal-ca"]
    path.write_bytes(certificate())

    assert policy.ca_pem == pem
    assert "internal-ca" not in repr(policy)
    assert "CERTIFICATE" not in repr(policy)


@pytest.mark.parametrize(
    "bundle",
    [
        b"not a certificate\n",
        certificate(ca=False),
        certificate(key_cert_sign=False),
        certificate(expired=True),
        certificate() + certificate(),
    ],
)
def test_loader_rejects_invalid_certificate_semantics_and_duplicate_bundle(
    tmp_path: Path, bundle: bytes
) -> None:
    if bundle.startswith(b"-----BEGIN") and bundle.count(b"BEGIN") == 2:
        first = bundle.split(b"-----END CERTIFICATE-----\n", 1)[0] + b"-----END CERTIFICATE-----\n"
        bundle = first + first
    workspace_policy(tmp_path, bundle)

    with pytest.raises(ConfigurationError):
        load_webhook_tls_trust_policies(tmp_path, now=NOW)


def test_loader_rejects_symlink_writable_oversized_and_foreign_data(tmp_path: Path) -> None:
    path = workspace_policy(tmp_path, certificate())
    path.chmod(0o666)
    with pytest.raises(ConfigurationError, match="safe bounded"):
        load_webhook_tls_trust_policies(tmp_path, now=NOW)

    path.chmod(0o600)
    path.write_bytes(b" " * (MAX_WEBHOOK_CA_BUNDLE_BYTES + 1))
    with pytest.raises(ConfigurationError, match="safe bounded"):
        load_webhook_tls_trust_policies(tmp_path, now=NOW)

    path.unlink()
    outside = tmp_path / "outside.pem"
    outside.write_bytes(certificate())
    path.symlink_to(outside)
    with pytest.raises(ConfigurationError, match="regular"):
        load_webhook_tls_trust_policies(tmp_path, now=NOW)

    path.unlink()
    path.write_bytes(certificate() + b"PRIVATE KEY")
    path.chmod(0o600)
    with pytest.raises(ConfigurationError, match="canonical"):
        load_webhook_tls_trust_policies(tmp_path, now=NOW)


def test_missing_configuration_has_no_implicit_trust_policy(tmp_path: Path) -> None:
    assert load_webhook_tls_trust_policies(tmp_path, now=NOW) == {}

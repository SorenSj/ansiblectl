"""Safe loading and validation of exclusive webhook CA trust snapshots."""

from __future__ import annotations

import os
import stat
from datetime import UTC, datetime
from pathlib import Path

import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from yaml.tokens import AliasToken, AnchorToken, TagToken

from ansiblectl.domain.errors import ConfigurationError
from ansiblectl.domain.webhook_tls_trust import (
    MAX_WEBHOOK_CA_CERTIFICATES,
    WebhookTlsTrustPolicy,
    parse_webhook_tls_trust_definitions,
)

MAX_WEBHOOK_TLS_TRUST_CONFIG_BYTES = 65_536
MAX_WEBHOOK_CA_BUNDLE_BYTES = 262_144


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[object, object]:
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError("duplicate mapping key")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def load_webhook_tls_trust_policies(
    workspace_root: Path, *, now: datetime | None = None
) -> dict[str, WebhookTlsTrustPolicy]:
    root = workspace_root.resolve()
    private = root / ".ansiblectl"
    values = _load_policy_document(private)
    if values is None:
        return {}
    definitions = parse_webhook_tls_trust_definitions(values, "workspace TLS trust configuration")
    instant = now or datetime.now(UTC)
    policies: dict[str, WebhookTlsTrustPolicy] = {}
    for policy_id, definition in definitions.items():
        path = private / "trust" / Path(*definition.ca_bundle_path.parts)
        encoded = _read_ca_bundle(root, private / "trust", path)
        policies[policy_id] = WebhookTlsTrustPolicy(
            policy_id, _validate_ca_bundle(encoded, instant)
        )
    return policies


def _load_policy_document(private: Path) -> dict[str, object] | None:
    path = private / "webhook-tls-trust.yaml"
    encoded = _read_bounded_file(path, MAX_WEBHOOK_TLS_TRUST_CONFIG_BYTES, missing_ok=True)
    if encoded is None:
        return None
    try:
        text = encoded.decode("utf-8")
        if any(isinstance(token, (AliasToken, AnchorToken, TagToken)) for token in yaml.scan(text)):
            raise ConfigurationError("Webhook TLS trust YAML uses forbidden syntax.")
        values = yaml.load(text, Loader=_UniqueKeyLoader)
    except (UnicodeDecodeError, yaml.YAMLError) as error:
        raise ConfigurationError(
            "Webhook TLS trust configuration could not be parsed safely."
        ) from error
    if not isinstance(values, dict):
        raise ConfigurationError("Webhook TLS trust configuration must be a YAML mapping.")
    return values


def _read_ca_bundle(root: Path, trust_root: Path, path: Path) -> bytes:
    if (
        path.is_symlink()
        or trust_root.parent.is_symlink()
        or any(parent.is_symlink() for parent in path.parents if parent.is_relative_to(trust_root))
    ):
        raise ConfigurationError("Webhook TLS CA bundle must remain in a regular trust directory.")
    try:
        if not path.resolve().is_relative_to(trust_root.resolve()):
            raise ConfigurationError(
                "Webhook TLS CA bundle must remain inside the trust directory."
            )
    except OSError as error:
        raise ConfigurationError("Webhook TLS CA bundle could not be resolved safely.") from error
    encoded = _read_bounded_file(path, MAX_WEBHOOK_CA_BUNDLE_BYTES, missing_ok=False, secure=True)
    assert encoded is not None
    return encoded


def _read_bounded_file(
    path: Path, limit: int, *, missing_ok: bool, secure: bool = False
) -> bytes | None:
    if path.is_symlink():
        raise ConfigurationError("Webhook TLS trust input must be a regular file.")
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except FileNotFoundError as error:
        if missing_ok:
            return None
        raise ConfigurationError("Webhook TLS trust input is unavailable.") from error
    except OSError as error:
        raise ConfigurationError("Webhook TLS trust input could not be read safely.") from error
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > limit
            or (secure and (metadata.st_uid != os.geteuid() or metadata.st_mode & 0o022))
        ):
            raise ConfigurationError("Webhook TLS trust input is not a safe bounded file.")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            encoded = handle.read(limit + 1)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(encoded) > limit:
        raise ConfigurationError("Webhook TLS trust input is not a safe bounded file.")
    return encoded


def _validate_ca_bundle(encoded: bytes, now: datetime) -> bytes:
    try:
        certificates = x509.load_pem_x509_certificates(encoded)
    except ValueError as error:
        raise ConfigurationError("Webhook TLS CA bundle is invalid.") from error
    if not 1 <= len(certificates) <= MAX_WEBHOOK_CA_CERTIFICATES:
        raise ConfigurationError("Webhook TLS CA bundle certificate count is invalid.")
    canonical = b"".join(cert.public_bytes(serialization.Encoding.PEM) for cert in certificates)
    if encoded != canonical:
        raise ConfigurationError("Webhook TLS CA bundle encoding is not canonical.")
    fingerprints: set[bytes] = set()
    for certificate in certificates:
        fingerprint = certificate.fingerprint(hashes.SHA256())
        if fingerprint in fingerprints:
            raise ConfigurationError("Webhook TLS CA bundle contains duplicate certificates.")
        fingerprints.add(fingerprint)
        try:
            constraints = certificate.extensions.get_extension_for_class(x509.BasicConstraints)
        except x509.ExtensionNotFound as error:
            raise ConfigurationError("Webhook TLS CA certificate semantics are invalid.") from error
        if not constraints.critical or not constraints.value.ca:
            raise ConfigurationError("Webhook TLS CA certificate semantics are invalid.")
        try:
            usage = certificate.extensions.get_extension_for_class(x509.KeyUsage).value
        except x509.ExtensionNotFound:
            pass
        else:
            if not usage.key_cert_sign:
                raise ConfigurationError("Webhook TLS CA certificate semantics are invalid.")
        if not certificate.not_valid_before_utc <= now <= certificate.not_valid_after_utc:
            raise ConfigurationError("Webhook TLS CA certificate validity is invalid.")
    return canonical


__all__ = [
    "MAX_WEBHOOK_CA_BUNDLE_BYTES",
    "MAX_WEBHOOK_TLS_TRUST_CONFIG_BYTES",
    "load_webhook_tls_trust_policies",
]

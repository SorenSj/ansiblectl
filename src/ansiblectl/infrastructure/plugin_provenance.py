"""Ed25519 and artifact verification for validated plugin provenance."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import BinaryIO

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ansiblectl.domain.plugin_trust import (
    PluginProvenance,
    PluginTrustError,
    PluginTrustReason,
    canonical_payload,
)
from ansiblectl.domain.plugins import ProviderDescriptor

_CHUNK_SIZE = 1024 * 1024


def signing_key_id(public_key: bytes) -> str:
    """Return the canonical opaque identifier for raw Ed25519 public-key bytes."""

    if len(public_key) != 32:
        raise ValueError("Ed25519 public keys must contain exactly 32 bytes.")
    return f"ed25519:sha256:{hashlib.sha256(public_key).hexdigest()}"


def verify_provenance(
    provenance: PluginProvenance,
    artifact: BinaryIO,
    descriptor: ProviderDescriptor,
    trusted_keys: Mapping[str, bytes],
) -> None:
    """Verify key, signature, bytes, and manifest agreement before plugin import."""

    public_bytes = trusted_keys.get(provenance.signing_key_id)
    if (
        public_bytes is None
        or len(public_bytes) != 32
        or signing_key_id(public_bytes) != provenance.signing_key_id
    ):
        raise PluginTrustError(PluginTrustReason.SIGNING_KEY_UNTRUSTED)
    try:
        public_key = Ed25519PublicKey.from_public_bytes(public_bytes)
        public_key.verify(provenance.signature, canonical_payload(provenance))
    except (InvalidSignature, ValueError) as error:
        raise PluginTrustError(PluginTrustReason.SIGNATURE_INVALID) from error
    digest = hashlib.sha256()
    while chunk := artifact.read(_CHUNK_SIZE):
        if not isinstance(chunk, bytes):
            raise TypeError("Plugin artifact streams must return bytes.")
        digest.update(chunk)
    if f"sha256:{digest.hexdigest()}" != provenance.artifact_digest:
        raise PluginTrustError(PluginTrustReason.ARTIFACT_DIGEST_MISMATCH)
    if (
        provenance.provider_identity != descriptor.identity
        or provenance.plugin_version != descriptor.version
        or provenance.sdk_compatibility != descriptor.sdk_compatibility
    ):
        raise PluginTrustError(PluginTrustReason.MANIFEST_PROVENANCE_MISMATCH)


__all__ = ["signing_key_id", "verify_provenance"]

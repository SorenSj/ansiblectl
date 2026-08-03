"""Fixed-vector tests for Ed25519 plugin provenance verification."""

import base64
import hashlib
import io
import json

import pytest

from ansiblectl.domain.plugin_trust import (
    PluginProvenance,
    PluginTrustError,
    PluginTrustReason,
    parse_provenance,
)
from ansiblectl.domain.plugins import ProviderDescriptor
from ansiblectl.infrastructure.plugin_provenance import signing_key_id, verify_provenance

_ARTIFACT = b"fixed plugin artifact\n"
_PUBLIC_BYTES = bytes.fromhex("03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8")
_SIGNATURE = (
    "0SpY68PHdAVeLgMJQG4wTlhk8aDObItOiZkNXWwg_4wxJceGeCyBwbHP3pdVRpX7dXKhGo2z00YG_cUKKy7sBg"
)


def _fixture() -> tuple[PluginProvenance, ProviderDescriptor, bytes]:
    values: dict[str, object] = {
        "schema_version": 1,
        "provider_identity": "example.provider",
        "plugin_version": "1.2.3",
        "sdk_compatibility": "0.1",
        "artifact_digest": f"sha256:{hashlib.sha256(_ARTIFACT).hexdigest()}",
        "origin": "https://plugins.example.test/releases",
        "signing_key_id": signing_key_id(_PUBLIC_BYTES),
        "signature": _SIGNATURE,
    }
    return parse_provenance(json.dumps(values).encode()), _descriptor(), _PUBLIC_BYTES


def _descriptor() -> ProviderDescriptor:
    return ProviderDescriptor(
        "example.provider", "1.2.3", "0.1", ("provider",), "schema.json", (), "manifest"
    )


def test_fixed_vector_verifies_exact_artifact_and_manifest() -> None:
    provenance, descriptor, public_bytes = _fixture()

    verify_provenance(
        provenance,
        io.BytesIO(_ARTIFACT),
        descriptor,
        {signing_key_id(public_bytes): public_bytes},
    )


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ("unknown_key", PluginTrustReason.SIGNING_KEY_UNTRUSTED),
        ("signature", PluginTrustReason.SIGNATURE_INVALID),
        ("artifact", PluginTrustReason.ARTIFACT_DIGEST_MISMATCH),
        ("manifest", PluginTrustReason.MANIFEST_PROVENANCE_MISMATCH),
    ],
)
def test_verification_returns_only_stable_failure_reason(
    change: str, reason: PluginTrustReason
) -> None:
    provenance, descriptor, public_bytes = _fixture()
    keys = {signing_key_id(public_bytes): public_bytes}
    artifact = _ARTIFACT
    if change == "unknown_key":
        keys = {}
    elif change == "signature":
        provenance = parse_provenance(
            json.dumps(
                {
                    **provenance.signed_fields(),
                    "signature": base64.urlsafe_b64encode(b"x" * 64).rstrip(b"=").decode(),
                }
            ).encode()
        )
    elif change == "artifact":
        artifact += b"changed"
    else:
        descriptor = ProviderDescriptor(
            "other.provider", "1.2.3", "0.1", (), "schema.json", (), "manifest"
        )

    with pytest.raises(PluginTrustError) as raised:
        verify_provenance(
            provenance,
            io.BytesIO(artifact),
            descriptor,
            keys,
        )

    assert raised.value.reason is reason
    assert raised.value.context == {"reason": reason.value}
    assert public_bytes.hex() not in str(raised.value.context)

"""Fixed-vector tests for Ed25519 plugin provenance verification."""

import base64
import hashlib
import io
import json
from dataclasses import replace

import pytest

from ansiblectl.domain.plugin_policy import PluginPolicyRule, UnattendedPluginPolicy
from ansiblectl.domain.plugin_trust import (
    PluginProvenance,
    PluginTrustError,
    PluginTrustReason,
    parse_provenance,
)
from ansiblectl.domain.plugins import ProviderDescriptor
from ansiblectl.infrastructure.plugin_provenance import (
    signing_key_id,
    verify_plugin_trust,
    verify_provenance,
)

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


def _trusted_origins(public_bytes: bytes) -> dict[tuple[str, str], frozenset[str]]:
    return {
        ("example.provider", signing_key_id(public_bytes)): frozenset(
            {"https://plugins.example.test/releases"}
        )
    }


def test_fixed_vector_verifies_exact_artifact_and_manifest() -> None:
    provenance, descriptor, public_bytes = _fixture()

    verify_provenance(
        provenance,
        io.BytesIO(_ARTIFACT),
        descriptor,
        {signing_key_id(public_bytes): public_bytes},
        _trusted_origins(public_bytes),
    )


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ("unknown_key", PluginTrustReason.SIGNING_KEY_UNTRUSTED),
        ("signature", PluginTrustReason.SIGNATURE_INVALID),
        ("artifact", PluginTrustReason.ARTIFACT_DIGEST_MISMATCH),
        ("manifest", PluginTrustReason.MANIFEST_PROVENANCE_MISMATCH),
        ("origin", PluginTrustReason.ORIGIN_UNTRUSTED),
    ],
)
def test_verification_returns_only_stable_failure_reason(
    change: str, reason: PluginTrustReason
) -> None:
    provenance, descriptor, public_bytes = _fixture()
    keys = {signing_key_id(public_bytes): public_bytes}
    artifact = _ARTIFACT
    origins = _trusted_origins(public_bytes)
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
    elif change == "manifest":
        descriptor = ProviderDescriptor(
            "other.provider", "1.2.3", "0.1", (), "schema.json", (), "manifest"
        )
    else:
        origins = {}

    with pytest.raises(PluginTrustError) as raised:
        verify_provenance(
            provenance,
            io.BytesIO(artifact),
            descriptor,
            keys,
            origins,
        )

    assert raised.value.reason is reason
    assert raised.value.context == {"reason": reason.value}
    assert public_bytes.hex() not in str(raised.value.context)


def test_origin_trust_is_bound_to_provider_and_signing_key() -> None:
    provenance, descriptor, public_bytes = _fixture()
    key_id = signing_key_id(public_bytes)

    with pytest.raises(PluginTrustError) as raised:
        verify_provenance(
            provenance,
            io.BytesIO(_ARTIFACT),
            descriptor,
            {key_id: public_bytes},
            {("other.provider", key_id): frozenset({provenance.origin})},
        )

    assert raised.value.reason is PluginTrustReason.ORIGIN_UNTRUSTED


def test_manifest_mismatch_precedes_origin_rejection() -> None:
    provenance, _, public_bytes = _fixture()
    descriptor = ProviderDescriptor(
        "other.provider", "1.2.3", "0.1", (), "schema.json", (), "manifest"
    )

    with pytest.raises(PluginTrustError) as raised:
        verify_provenance(
            provenance,
            io.BytesIO(_ARTIFACT),
            descriptor,
            {signing_key_id(public_bytes): public_bytes},
            {},
        )

    assert raised.value.reason is PluginTrustReason.MANIFEST_PROVENANCE_MISMATCH


def test_complete_trust_verification_returns_unattended_permission_grants() -> None:
    provenance, descriptor, public_bytes = _fixture()
    descriptor = replace(descriptor, permissions=("network",))
    policy = UnattendedPluginPolicy(
        allow=(
            PluginPolicyRule(
                provider_identity=provenance.provider_identity,
                permissions=frozenset({"network"}),
                artifact_digest=provenance.artifact_digest,
                signing_key_id=provenance.signing_key_id,
                origins=frozenset({provenance.origin}),
            ),
        )
    )

    decision = verify_plugin_trust(
        provenance,
        io.BytesIO(_ARTIFACT),
        descriptor,
        {signing_key_id(public_bytes): public_bytes},
        _trusted_origins(public_bytes),
        policy,
    )

    assert decision.trusted is True
    assert decision.granted_permissions == ("network",)
    assert decision.reasons == ()


def test_cryptographic_failure_precedes_missing_unattended_policy() -> None:
    provenance, descriptor, public_bytes = _fixture()

    with pytest.raises(PluginTrustError) as raised:
        verify_plugin_trust(
            replace(provenance, signature=b"x" * 64),
            io.BytesIO(_ARTIFACT),
            descriptor,
            {signing_key_id(public_bytes): public_bytes},
            _trusted_origins(public_bytes),
            None,
        )

    assert raised.value.reason is PluginTrustReason.SIGNATURE_INVALID

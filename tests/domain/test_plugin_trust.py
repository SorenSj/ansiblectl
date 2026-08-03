"""Domain contract tests for canonical plugin provenance."""

import base64
import json

import pytest

from ansiblectl.domain.plugin_trust import (
    MAX_PROVENANCE_BYTES,
    PluginTrustError,
    PluginTrustReason,
    canonical_payload,
    parse_provenance,
)


def _statement(**overrides: object) -> bytes:
    values: dict[str, object] = {
        "schema_version": 1,
        "provider_identity": "example.provider",
        "plugin_version": "1.2.3",
        "sdk_compatibility": "0.1",
        "artifact_digest": f"sha256:{'a' * 64}",
        "origin": "https://plugins.example.test/releases",
        "signing_key_id": f"ed25519:sha256:{'b' * 64}",
        "signature": base64.urlsafe_b64encode(b"s" * 64).rstrip(b"=").decode(),
    }
    values.update(overrides)
    return json.dumps(values).encode()


def test_parse_provenance_returns_canonical_signed_payload() -> None:
    provenance = parse_provenance(_statement())

    assert provenance.provider_identity == "example.provider"
    assert provenance.signature == b"s" * 64
    assert canonical_payload(provenance) == (
        b"ansiblectl-plugin-provenance-v1\n"
        b'{"artifact_digest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
        b'"origin":"https://plugins.example.test/releases","plugin_version":"1.2.3",'
        b'"provider_identity":"example.provider","schema_version":1,'
        b'"sdk_compatibility":"0.1","signing_key_id":'
        b'"ed25519:sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}'
    )


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"{" + b" " * MAX_PROVENANCE_BYTES + b"}",
        _statement(extra="unknown"),
        _statement(origin="HTTPS://plugins.example.test"),
        _statement(origin="local:../escape"),
        _statement(signature="not-canonical="),
        _statement(provider_identity="Uppercase"),
    ],
)
def test_parse_provenance_rejects_noncanonical_or_unknown_data(data: bytes) -> None:
    with pytest.raises(PluginTrustError) as raised:
        parse_provenance(data)

    assert raised.value.reason is PluginTrustReason.PROVENANCE_INVALID
    assert raised.value.context == {"reason": "PROVENANCE_INVALID"}


def test_parse_provenance_rejects_duplicate_json_keys() -> None:
    data = _statement().replace(b'"schema_version": 1', b'"schema_version": 1, "schema_version": 1')

    with pytest.raises(PluginTrustError) as raised:
        parse_provenance(data)

    assert raised.value.reason is PluginTrustReason.PROVENANCE_INVALID

"""Exclusive webhook TLS trust definition tests."""

from pathlib import PurePosixPath

import pytest

from ansiblectl.domain.errors import ConfigurationError
from ansiblectl.domain.webhook_tls_trust import parse_webhook_tls_trust_definitions


def document(
    path: object = "internal/root-ca.pem", policy_id: object = "internal-ca"
) -> dict[str, object]:
    return {"schema_version": 1, "policies": {policy_id: {"ca_bundle": path}}}


def test_definition_parses_one_canonical_relative_bundle_path() -> None:
    definition = parse_webhook_tls_trust_definitions(document(), "workspace")["internal-ca"]

    assert definition.ca_bundle_path == PurePosixPath("internal/root-ca.pem")
    assert "internal-ca" not in repr(definition)
    assert "root-ca.pem" not in repr(definition)


@pytest.mark.parametrize(
    "path",
    [
        "/root.pem",
        "../root.pem",
        "./root.pem",
        "internal//root.pem",
        "internal\\root.pem",
        "ROOT.pem",
        "root.crt",
        "høst.pem",
        "x" * 256,
    ],
)
def test_definition_rejects_noncanonical_or_escaping_paths(path: str) -> None:
    with pytest.raises(ConfigurationError, match="path"):
        parse_webhook_tls_trust_definitions(document(path), "workspace")


def test_definition_rejects_unknown_fields_identifiers_bounds_and_schema() -> None:
    with pytest.raises(ConfigurationError, match="identifier"):
        parse_webhook_tls_trust_definitions(document(policy_id="UPPER"), "workspace")
    with pytest.raises(ConfigurationError, match="definition"):
        parse_webhook_tls_trust_definitions(
            {"schema_version": 1, "policies": {"ca": {"ca_bundle": "root.pem", "extra": 1}}},
            "workspace",
        )
    with pytest.raises(ConfigurationError, match="schema_version"):
        parse_webhook_tls_trust_definitions({"schema_version": 2, "policies": {}}, "workspace")
    with pytest.raises(ConfigurationError, match="count"):
        parse_webhook_tls_trust_definitions(
            {
                "schema_version": 1,
                "policies": {f"ca-{index}": {"ca_bundle": "root.pem"} for index in range(33)},
            },
            "workspace",
        )

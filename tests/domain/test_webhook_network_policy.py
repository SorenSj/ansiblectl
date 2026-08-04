"""Named private webhook network policy model tests."""

import ipaddress

import pytest

from ansiblectl.domain.errors import ConfigurationError
from ansiblectl.domain.webhook_network_policy import parse_webhook_network_policies


def document(*cidrs: object, policy_id: object = "automation.private") -> dict[str, object]:
    return {
        "schema_version": 1,
        "policies": {policy_id: {"allowed_cidrs": list(cidrs)}},
    }


def test_policy_parses_bounded_canonical_ipv4_and_ipv6_networks() -> None:
    policy = parse_webhook_network_policies(
        document("10.20.0.0/16", "172.16.8.0/24", "fd12:3456::/48"), "workspace"
    )["automation.private"]

    assert policy.allowed_networks == (
        ipaddress.ip_network("10.20.0.0/16"),
        ipaddress.ip_network("172.16.8.0/24"),
        ipaddress.ip_network("fd12:3456::/48"),
    )
    assert "automation.private" not in repr(policy)
    assert "10.20.0.0" not in repr(policy)


@pytest.mark.parametrize(
    "cidr",
    [
        "10.0.0.1/8",
        "10.0.0.0/255.0.0.0",
        "10.0.0.0",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "192.0.2.0/24",
        "198.18.0.0/15",
        "224.0.0.0/4",
        "::1/128",
        "fe80::/10",
        "ff00::/8",
        "::ffff:10.0.0.0/104",
        "FD00::/8",
    ],
)
def test_policy_rejects_ambiguous_or_unapproved_networks(cidr: str) -> None:
    with pytest.raises(ConfigurationError, match="canonical|allowed"):
        parse_webhook_network_policies(document(cidr), "workspace")


@pytest.mark.parametrize("policy_id", ["UPPER", "9policy", "bad key", "p" * 129])
def test_policy_rejects_noncanonical_identifiers(policy_id: str) -> None:
    with pytest.raises(ConfigurationError, match="identifier"):
        parse_webhook_network_policies(document("10.0.0.0/8", policy_id=policy_id), "workspace")


def test_policy_rejects_overlaps_bounds_unknown_fields_and_schema() -> None:
    with pytest.raises(ConfigurationError, match="overlap"):
        parse_webhook_network_policies(document("10.0.0.0/8", "10.20.0.0/16"), "workspace")
    with pytest.raises(ConfigurationError, match="CIDRs"):
        parse_webhook_network_policies(
            document(*[f"10.{index}.0.0/16" for index in range(17)]), "workspace"
        )
    invalid_definition = document("10.0.0.0/8")
    invalid_definition["policies"] = {"private": {"allowed_cidrs": ["10.0.0.0/8"], "extra": True}}
    with pytest.raises(ConfigurationError, match="definition"):
        parse_webhook_network_policies(invalid_definition, "workspace")
    with pytest.raises(ConfigurationError, match="schema_version"):
        parse_webhook_network_policies({"schema_version": 2, "policies": {}}, "workspace")

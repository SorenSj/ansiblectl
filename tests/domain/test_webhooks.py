"""Outbound webhook endpoint and destination-policy tests."""

import pytest

from ansiblectl.domain.errors import ConfigurationError
from ansiblectl.domain.webhook_network_policy import parse_webhook_network_policies
from ansiblectl.domain.webhook_tls_trust import WebhookTlsTrustPolicy
from ansiblectl.domain.webhooks import parse_webhook_endpoints, resolve_webhook_destination


class Resolver:
    def __init__(self, *addresses: str) -> None:
        self.addresses = addresses
        self.request: tuple[str, int] | None = None

    def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        self.request = (hostname, port)
        return self.addresses


def endpoint_document(*, schema_version: int = 1, **overrides: object) -> dict[str, object]:
    definition: dict[str, object] = {
        "url": "https://hooks.example.test/events?source=ansiblectl",
        "allowed_hostnames": ["hooks.example.test"],
        "bearer_secret": "env:WEBHOOK_TOKEN",
        "connect_timeout_seconds": 5,
        "read_timeout_seconds": 20,
    }
    definition.update(overrides)
    return {"schema_version": schema_version, "endpoints": {"audit.primary": definition}}


def private_policies() -> dict[str, object]:
    return {
        "schema_version": 1,
        "policies": {"receiver": {"allowed_cidrs": ["10.20.0.0/16", "fd12:3456::/48"]}},
    }


def test_endpoint_configuration_is_typed_and_contains_only_a_secret_reference() -> None:
    endpoint = parse_webhook_endpoints(endpoint_document(), "workspace")["audit.primary"]

    assert endpoint.hostname == "hooks.example.test"
    assert endpoint.port == 443
    assert endpoint.allowed_hostnames == frozenset({"hooks.example.test"})
    assert str(endpoint.bearer_secret) == "env:WEBHOOK_TOKEN"
    assert endpoint.connect_timeout_seconds == 5
    assert endpoint.read_timeout_seconds == 20
    assert endpoint.schema_version == 1
    assert endpoint.network_policy is None
    assert "credential-value" not in repr(endpoint)


@pytest.mark.parametrize(
    "url",
    [
        "http://hooks.example.test/events",
        "https://user@hooks.example.test/events",
        "https://hooks.example.test/events#fragment",
        "https://127.0.0.1/events",
        "https://Hooks.example.test/events",
        "https://høoks.example.test/events",
        "https://hooks.example.test.:443/events",
    ],
)
def test_endpoint_rejects_noncanonical_or_unsafe_urls(url: str) -> None:
    with pytest.raises(ConfigurationError, match="canonical|IP literal"):
        parse_webhook_endpoints(endpoint_document(url=url), "workspace")


def test_endpoint_requires_exact_hostname_allowlist_and_bounded_timeouts() -> None:
    with pytest.raises(ConfigurationError, match="explicitly allowed"):
        parse_webhook_endpoints(
            endpoint_document(allowed_hostnames=["other.example.test"]), "workspace"
        )
    with pytest.raises(ConfigurationError, match="between 1 and 60"):
        parse_webhook_endpoints(endpoint_document(read_timeout_seconds=61), "workspace")


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.1", "169.254.1.1", "224.0.0.1", "::1", "fc00::1"],
)
def test_destination_policy_rejects_any_non_global_address(address: str) -> None:
    endpoint = parse_webhook_endpoints(endpoint_document(), "workspace")["audit.primary"]

    with pytest.raises(ConfigurationError, match="denied"):
        resolve_webhook_destination(endpoint, Resolver("8.8.8.8", address))


def test_destination_preserves_only_validated_canonical_addresses_for_connection() -> None:
    endpoint = parse_webhook_endpoints(endpoint_document(), "workspace")["audit.primary"]
    resolver = Resolver("8.8.8.8", "2001:4860:4860::8888", "8.8.8.8")

    destination = resolve_webhook_destination(endpoint, resolver)

    assert resolver.request == ("hooks.example.test", 443)
    assert destination.hostname == "hooks.example.test"
    assert destination.addresses == ("8.8.8.8", "2001:4860:4860::8888")


def test_endpoint_document_rejects_unknown_fields_and_invalid_secret_reference() -> None:
    with pytest.raises(ConfigurationError, match="Unknown field 'header'"):
        parse_webhook_endpoints(endpoint_document(header="unsafe"), "workspace")
    with pytest.raises(ConfigurationError, match="provider:key"):
        parse_webhook_endpoints(endpoint_document(bearer_secret="raw-secret"), "workspace")


def test_schema_two_binds_one_exact_immutable_private_policy() -> None:
    policies = parse_webhook_network_policies(private_policies(), "policy")
    endpoint = parse_webhook_endpoints(
        endpoint_document(schema_version=2, network_policy="receiver"), "workspace", policies
    )["audit.primary"]

    assert endpoint.schema_version == 2
    assert endpoint.network_policy is policies["receiver"]
    assert "receiver" not in repr(endpoint)
    assert "10.20.0.0" not in repr(endpoint)


def test_schema_one_rejects_policy_field_and_schema_two_fails_closed_on_missing_policy() -> None:
    with pytest.raises(ConfigurationError, match="Unknown field"):
        parse_webhook_endpoints(endpoint_document(network_policy="receiver"), "workspace")
    with pytest.raises(ConfigurationError, match="not configured") as caught:
        parse_webhook_endpoints(
            endpoint_document(schema_version=2, network_policy="sentinel-policy"),
            "workspace",
        )
    assert "sentinel-policy" not in str(caught.value)


def test_schema_three_binds_exact_immutable_tls_trust_independently() -> None:
    trust = WebhookTlsTrustPolicy("sentinel-trust", b"sentinel-certificate")
    endpoint = parse_webhook_endpoints(
        endpoint_document(schema_version=3, tls_trust_policy="sentinel-trust"),
        "workspace",
        tls_trust_policies={"sentinel-trust": trust},
    )["audit.primary"]

    assert endpoint.schema_version == 3
    assert endpoint.network_policy is None
    assert endpoint.tls_trust_policy is trust
    assert "sentinel-trust" not in repr(endpoint)
    assert "sentinel-certificate" not in repr(endpoint)


def test_older_schemas_reject_tls_trust_and_schema_three_requires_exact_policy() -> None:
    for schema_version in (1, 2):
        with pytest.raises(ConfigurationError, match="Unknown field"):
            parse_webhook_endpoints(
                endpoint_document(schema_version=schema_version, tls_trust_policy="private-ca"),
                "workspace",
            )
    with pytest.raises(ConfigurationError, match="TLS trust policy reference"):
        parse_webhook_endpoints(
            endpoint_document(schema_version=3, tls_trust_policy="sentinel-trust"),
            "workspace",
        )


def test_private_policy_requires_every_resolved_address_in_exact_ranges() -> None:
    policies = parse_webhook_network_policies(private_policies(), "policy")
    endpoint = parse_webhook_endpoints(
        endpoint_document(schema_version=2, network_policy="receiver"), "workspace", policies
    )["audit.primary"]

    destination = resolve_webhook_destination(
        endpoint, Resolver("10.20.1.8", "fd12:3456::8", "10.20.1.8")
    )

    assert destination.addresses == ("10.20.1.8", "fd12:3456::8")


@pytest.mark.parametrize(
    "addresses",
    [
        ("10.20.1.8", "10.21.0.1"),
        ("10.20.1.8", "8.8.8.8"),
        ("127.0.0.1",),
        ("169.254.169.254",),
        ("100.64.0.1",),
        ("::ffff:a14:108",),
        ("FD12:3456::8",),
    ],
)
def test_private_policy_denies_mixed_forbidden_mapped_and_noncanonical_answers(
    addresses: tuple[str, ...],
) -> None:
    policies = parse_webhook_network_policies(private_policies(), "policy")
    endpoint = parse_webhook_endpoints(
        endpoint_document(schema_version=2, network_policy="receiver"), "workspace", policies
    )["audit.primary"]

    with pytest.raises(ConfigurationError, match="denied"):
        resolve_webhook_destination(endpoint, Resolver(*addresses))

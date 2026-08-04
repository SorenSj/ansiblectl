"""Outbound webhook endpoint and destination-policy tests."""

import pytest

from ansiblectl.domain.errors import ConfigurationError
from ansiblectl.domain.webhooks import parse_webhook_endpoints, resolve_webhook_destination


class Resolver:
    def __init__(self, *addresses: str) -> None:
        self.addresses = addresses
        self.request: tuple[str, int] | None = None

    def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        self.request = (hostname, port)
        return self.addresses


def endpoint_document(**overrides: object) -> dict[str, object]:
    definition: dict[str, object] = {
        "url": "https://hooks.example.test/events?source=ansiblectl",
        "allowed_hostnames": ["hooks.example.test"],
        "bearer_secret": "env:WEBHOOK_TOKEN",
        "connect_timeout_seconds": 5,
        "read_timeout_seconds": 20,
    }
    definition.update(overrides)
    return {"schema_version": 1, "endpoints": {"audit.primary": definition}}


def test_endpoint_configuration_is_typed_and_contains_only_a_secret_reference() -> None:
    endpoint = parse_webhook_endpoints(endpoint_document(), "workspace")["audit.primary"]

    assert endpoint.hostname == "hooks.example.test"
    assert endpoint.port == 443
    assert endpoint.allowed_hostnames == frozenset({"hooks.example.test"})
    assert str(endpoint.bearer_secret) == "env:WEBHOOK_TOKEN"
    assert endpoint.connect_timeout_seconds == 5
    assert endpoint.read_timeout_seconds == 20
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

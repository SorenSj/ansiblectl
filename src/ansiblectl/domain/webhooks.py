"""Fail-closed outbound HTTPS webhook endpoint contracts."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol
from urllib.parse import urlsplit

from ansiblectl.domain.errors import ConfigurationError
from ansiblectl.domain.secrets import SecretMaterial, SecretReference
from ansiblectl.domain.webhook_network_policy import WebhookNetworkPolicy
from ansiblectl.domain.webhook_tls_trust import WebhookTlsTrustPolicy

WEBHOOK_CONFIGURATION_SCHEMA_VERSION = 6
MAX_WEBHOOK_TIMEOUT_SECONDS = 60
MAX_WEBHOOK_PAYLOAD_BYTES = 262_144
MAX_WEBHOOK_BATCH_EVENTS = 100
_ENDPOINT_ID_PATTERN = re.compile(r"[a-z][a-z0-9._-]{0,127}")
_DNS_LABEL_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_ENDPOINT_FIELDS = {
    "allowed_hostnames",
    "bearer_secret",
    "connect_timeout_seconds",
    "read_timeout_seconds",
    "url",
}
_ENDPOINT_FIELDS_V2 = _ENDPOINT_FIELDS | {"network_policy"}
_ENDPOINT_FIELDS_V3 = _ENDPOINT_FIELDS_V2 | {"tls_trust_policy"}
_ENDPOINT_FIELDS_V4 = _ENDPOINT_FIELDS_V3 | {"signature_secret"}
_ENDPOINT_FIELDS_V5 = _ENDPOINT_FIELDS_V4 | {"signature_version"}
_ENDPOINT_FIELDS_V6 = _ENDPOINT_FIELDS_V5 | {
    "client_certificate_secret",
    "client_private_key_secret",
}


@dataclass(frozen=True, repr=False)
class WebhookEndpoint:
    """One validated named HTTPS destination without secret material."""

    endpoint_id: str
    url: str
    hostname: str
    port: int
    allowed_hostnames: frozenset[str]
    bearer_secret: SecretReference | None
    connect_timeout_seconds: int
    read_timeout_seconds: int
    network_policy: WebhookNetworkPolicy | None = None
    tls_trust_policy: WebhookTlsTrustPolicy | None = None
    signature_secret: SecretReference | None = None
    signature_version: int | None = None
    client_certificate_secret: SecretReference | None = None
    client_private_key_secret: SecretReference | None = None
    schema_version: int = WEBHOOK_CONFIGURATION_SCHEMA_VERSION

    def __repr__(self) -> str:
        return (
            "WebhookEndpoint(endpoint_id=<redacted>, url=<redacted>, "
            "network_policy=<redacted>, tls_trust_policy=<redacted>, "
            "signature_secret=<redacted>, signature_version=<redacted>, "
            "client_identity=<redacted>)"
        )


@dataclass(frozen=True)
class WebhookDestination:
    """Validated resolution result that a connector must use without re-resolution."""

    hostname: str
    port: int
    addresses: tuple[str, ...]


class WebhookClientIdentityMaterial(Protocol):
    """Opaque request-local client identity consumed only by a TLS transport."""

    def reveal_for_transport(self) -> tuple[bytes, bytes]: ...


@dataclass(frozen=True, repr=False)
class WebhookRequest:
    """One bounded request whose representation omits body and credential material."""

    body: bytes
    headers: Mapping[str, str]
    bearer_material: SecretMaterial | None = None
    client_identity: WebhookClientIdentityMaterial | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))

    def __repr__(self) -> str:
        return (
            f"WebhookRequest(body=<redacted:{len(self.body)} bytes>, "
            f"headers={tuple(self.headers)}, bearer_material=<redacted>, "
            "client_identity=<redacted>)"
        )


class WebhookAddressResolver(Protocol):
    """Resolve one hostname for policy evaluation before connection."""

    def resolve(self, hostname: str, port: int) -> tuple[str, ...]: ...


class WebhookTransport(Protocol):
    """Send once using only the already-validated destination addresses."""

    def post(
        self,
        endpoint: WebhookEndpoint,
        destination: WebhookDestination,
        request: WebhookRequest,
    ) -> int: ...


class WebhookClock(Protocol):
    """Supply one canonical UTC Unix second for a request attempt."""

    def now_unix_seconds(self) -> int: ...


def parse_webhook_endpoints(
    values: Mapping[str, object],
    origin: str,
    policies: Mapping[str, WebhookNetworkPolicy] | None = None,
    tls_trust_policies: Mapping[str, WebhookTlsTrustPolicy] | None = None,
) -> Mapping[str, WebhookEndpoint]:
    """Parse one versioned endpoint document into immutable typed endpoints."""

    unknown = set(values) - {"schema_version", "endpoints"}
    if unknown:
        raise ConfigurationError(f"Unknown webhook field '{sorted(unknown)[0]}' in {origin}.")
    schema_version = values.get("schema_version")
    if schema_version not in {1, 2, 3, 4, 5, WEBHOOK_CONFIGURATION_SCHEMA_VERSION}:
        raise ConfigurationError(
            f"Webhook schema_version in {origin} must be 1, 2, 3, 4, 5, or "
            f"{WEBHOOK_CONFIGURATION_SCHEMA_VERSION}."
        )
    assert isinstance(schema_version, int)
    endpoints = values.get("endpoints")
    if not isinstance(endpoints, dict):
        raise ConfigurationError(f"Webhook endpoints in {origin} must be a mapping.")
    parsed: dict[str, WebhookEndpoint] = {}
    for endpoint_id, definition in endpoints.items():
        if not isinstance(endpoint_id, str) or not _ENDPOINT_ID_PATTERN.fullmatch(endpoint_id):
            raise ConfigurationError(f"Webhook endpoint identifier in {origin} is not canonical.")
        if not isinstance(definition, dict):
            raise ConfigurationError(
                f"Webhook endpoint '{endpoint_id}' in {origin} must be a mapping."
            )
        parsed[endpoint_id] = _parse_endpoint(
            endpoint_id,
            definition,
            origin,
            schema_version,
            policies or {},
            tls_trust_policies or {},
        )
    return MappingProxyType(parsed)


def resolve_webhook_destination(
    endpoint: WebhookEndpoint, resolver: WebhookAddressResolver
) -> WebhookDestination:
    """Resolve and require every address to satisfy one immutable endpoint policy."""

    try:
        candidates = resolver.resolve(endpoint.hostname, endpoint.port)
    except Exception as error:
        raise ConfigurationError("Webhook destination could not be resolved safely.") from error
    if not candidates:
        raise ConfigurationError("Webhook destination did not resolve to an allowed address.")
    addresses: list[str] = []
    for candidate in candidates:
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError as error:
            raise ConfigurationError("Webhook destination resolution was not canonical.") from error
        canonical = str(address)
        if canonical != candidate or not _address_allowed(endpoint, address):
            raise ConfigurationError("Webhook destination is denied by address policy.")
        if canonical not in addresses:
            addresses.append(canonical)
    return WebhookDestination(endpoint.hostname, endpoint.port, tuple(addresses))


def _parse_endpoint(
    endpoint_id: str,
    values: Mapping[str, object],
    origin: str,
    schema_version: int,
    policies: Mapping[str, WebhookNetworkPolicy],
    tls_trust_policies: Mapping[str, WebhookTlsTrustPolicy],
) -> WebhookEndpoint:
    if schema_version == 1:
        allowed_fields = _ENDPOINT_FIELDS
    elif schema_version == 2:
        allowed_fields = _ENDPOINT_FIELDS_V2
    elif schema_version == 3:
        allowed_fields = _ENDPOINT_FIELDS_V3
    elif schema_version == 4:
        allowed_fields = _ENDPOINT_FIELDS_V4
    elif schema_version == 5:
        allowed_fields = _ENDPOINT_FIELDS_V5
    else:
        allowed_fields = _ENDPOINT_FIELDS_V6
    unknown = set(values) - allowed_fields
    if unknown:
        raise ConfigurationError(
            f"Unknown field '{sorted(unknown)[0]}' for webhook endpoint "
            f"'{endpoint_id}' in {origin}."
        )
    url = values.get("url")
    if not isinstance(url, str) or len(url) > 2048 or any(ord(char) < 32 for char in url):
        raise ConfigurationError(f"Webhook endpoint '{endpoint_id}' URL is not canonical HTTPS.")
    hostname, port = _parse_https_url(url, endpoint_id)
    allowed_value = values.get("allowed_hostnames")
    if not isinstance(allowed_value, list) or not allowed_value:
        raise ConfigurationError(
            f"Webhook endpoint '{endpoint_id}' allowed_hostnames must be a non-empty list."
        )
    allowed = frozenset(_canonical_hostname(item, endpoint_id) for item in allowed_value)
    if hostname not in allowed:
        raise ConfigurationError(
            f"Webhook endpoint '{endpoint_id}' hostname must be explicitly allowed."
        )
    bearer_value = values.get("bearer_secret")
    bearer_secret = _parse_secret_reference(bearer_value, endpoint_id, "bearer_secret")
    signature_secret = _parse_secret_reference(
        values.get("signature_secret"), endpoint_id, "signature_secret"
    )
    signature_version = _parse_signature_version(
        values.get("signature_version"), signature_secret, endpoint_id, schema_version
    )
    client_certificate_secret, client_private_key_secret = _parse_client_identity_references(
        values.get("client_certificate_secret"),
        values.get("client_private_key_secret"),
        endpoint_id,
        schema_version,
    )
    connect_timeout = _positive_timeout(
        values.get("connect_timeout_seconds", 10), endpoint_id, "connect_timeout_seconds"
    )
    read_timeout = _positive_timeout(
        values.get("read_timeout_seconds", 30), endpoint_id, "read_timeout_seconds"
    )
    network_policy = _resolve_network_policy(values.get("network_policy"), policies, origin)
    tls_trust_policy = _resolve_tls_trust_policy(
        values.get("tls_trust_policy"), tls_trust_policies, origin
    )
    return WebhookEndpoint(
        endpoint_id=endpoint_id,
        url=url,
        hostname=hostname,
        port=port,
        allowed_hostnames=allowed,
        bearer_secret=bearer_secret,
        connect_timeout_seconds=connect_timeout,
        read_timeout_seconds=read_timeout,
        network_policy=network_policy,
        tls_trust_policy=tls_trust_policy,
        signature_secret=signature_secret,
        signature_version=signature_version,
        client_certificate_secret=client_certificate_secret,
        client_private_key_secret=client_private_key_secret,
        schema_version=schema_version,
    )


def _resolve_network_policy(
    value: object,
    policies: Mapping[str, WebhookNetworkPolicy],
    origin: str,
) -> WebhookNetworkPolicy | None:
    if value is None:
        return None
    if not isinstance(value, str) or value not in policies:
        raise ConfigurationError(f"Webhook network policy reference in {origin} is not configured.")
    return policies[value]


def _resolve_tls_trust_policy(
    value: object,
    policies: Mapping[str, WebhookTlsTrustPolicy],
    _origin: str,
) -> WebhookTlsTrustPolicy | None:
    if value is None:
        return None
    if not isinstance(value, str) or value not in policies:
        raise ConfigurationError("Webhook TLS trust policy reference is not configured.")
    return policies[value]


def _address_allowed(
    endpoint: WebhookEndpoint, address: ipaddress.IPv4Address | ipaddress.IPv6Address
) -> bool:
    if (
        address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
        or (isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None)
    ):
        return False
    if endpoint.network_policy is None:
        return address.is_global and not address.is_private
    return any(address in network for network in endpoint.network_policy.allowed_networks)


def _parse_https_url(url: str, endpoint_id: str) -> tuple[str, int]:
    try:
        parsed = urlsplit(url)
        port = parsed.port or 443
    except ValueError as error:
        raise ConfigurationError(
            f"Webhook endpoint '{endpoint_id}' URL is not canonical HTTPS."
        ) from error
    hostname = _canonical_hostname(parsed.hostname, endpoint_id)
    expected_netloc = hostname if parsed.port is None else f"{hostname}:{parsed.port}"
    if (
        parsed.scheme != "https"
        or parsed.netloc != expected_netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ConfigurationError(f"Webhook endpoint '{endpoint_id}' URL is not canonical HTTPS.")
    return hostname, port


def _canonical_hostname(value: object, endpoint_id: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 253:
        raise ConfigurationError(f"Webhook endpoint '{endpoint_id}' hostname is not canonical.")
    try:
        value.encode("ascii")
        ipaddress.ip_address(value)
    except UnicodeEncodeError as error:
        raise ConfigurationError(
            f"Webhook endpoint '{endpoint_id}' hostname is not canonical."
        ) from error
    except ValueError:
        pass
    else:
        raise ConfigurationError(f"Webhook endpoint '{endpoint_id}' cannot use an IP literal.")
    if (
        value != value.lower()
        or value.endswith(".")
        or any(not _DNS_LABEL_PATTERN.fullmatch(label) for label in value.split("."))
    ):
        raise ConfigurationError(f"Webhook endpoint '{endpoint_id}' hostname is not canonical.")
    return value


def _parse_secret_reference(value: object, endpoint_id: str, field: str) -> SecretReference | None:
    if value is None:
        return None
    if not isinstance(value, str) or value.count(":") != 1:
        raise ConfigurationError(
            f"Webhook endpoint '{endpoint_id}' {field} must be a provider:key reference."
        )
    provider, key = value.split(":", 1)
    try:
        return SecretReference(provider, key)
    except Exception as error:
        raise ConfigurationError(
            f"Webhook endpoint '{endpoint_id}' {field} must be a provider:key reference."
        ) from error


def _positive_timeout(value: object, endpoint_id: str, field: str) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 1
        or value > MAX_WEBHOOK_TIMEOUT_SECONDS
    ):
        raise ConfigurationError(
            f"Webhook endpoint '{endpoint_id}' {field} must be between 1 and "
            f"{MAX_WEBHOOK_TIMEOUT_SECONDS}."
        )
    return value


def _parse_signature_version(
    value: object,
    signature_secret: SecretReference | None,
    endpoint_id: str,
    schema_version: int,
) -> int | None:
    if schema_version < 5:
        return None
    if signature_secret is None:
        if value is not None:
            raise ConfigurationError(
                f"Webhook endpoint '{endpoint_id}' signature_version requires signature_secret."
            )
        return None
    allowed_versions = {2} if schema_version == 5 else {1, 2}
    if not isinstance(value, int) or isinstance(value, bool) or value not in allowed_versions:
        expected = "integer 2" if schema_version == 5 else "integer 1 or 2"
        raise ConfigurationError(
            f"Webhook endpoint '{endpoint_id}' signature_version must be {expected}."
        )
    return value


def _parse_client_identity_references(
    certificate_value: object,
    private_key_value: object,
    endpoint_id: str,
    schema_version: int,
) -> tuple[SecretReference | None, SecretReference | None]:
    if schema_version < 6:
        return None, None
    if certificate_value is None and private_key_value is None:
        return None, None
    if certificate_value is None or private_key_value is None:
        raise ConfigurationError(
            f"Webhook endpoint '{endpoint_id}' client identity requires both certificate and key."
        )
    certificate = _parse_secret_reference(
        certificate_value, endpoint_id, "client_certificate_secret"
    )
    private_key = _parse_secret_reference(
        private_key_value, endpoint_id, "client_private_key_secret"
    )
    assert certificate is not None and private_key is not None
    if certificate.provider != "file" or private_key.provider != "file":
        raise ConfigurationError(
            f"Webhook endpoint '{endpoint_id}' client identity requires file references."
        )
    if certificate == private_key:
        raise ConfigurationError(
            f"Webhook endpoint '{endpoint_id}' client identity references must be distinct."
        )
    return certificate, private_key


__all__ = [
    "MAX_WEBHOOK_PAYLOAD_BYTES",
    "MAX_WEBHOOK_BATCH_EVENTS",
    "MAX_WEBHOOK_TIMEOUT_SECONDS",
    "WEBHOOK_CONFIGURATION_SCHEMA_VERSION",
    "WebhookAddressResolver",
    "WebhookClock",
    "WebhookClientIdentityMaterial",
    "WebhookDestination",
    "WebhookEndpoint",
    "WebhookRequest",
    "WebhookTransport",
    "parse_webhook_endpoints",
    "resolve_webhook_destination",
]

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

WEBHOOK_CONFIGURATION_SCHEMA_VERSION = 1
MAX_WEBHOOK_TIMEOUT_SECONDS = 60
MAX_WEBHOOK_PAYLOAD_BYTES = 262_144
_ENDPOINT_ID_PATTERN = re.compile(r"[a-z][a-z0-9._-]{0,127}")
_DNS_LABEL_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_ENDPOINT_FIELDS = {
    "allowed_hostnames",
    "bearer_secret",
    "connect_timeout_seconds",
    "read_timeout_seconds",
    "url",
}


@dataclass(frozen=True)
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
    schema_version: int = WEBHOOK_CONFIGURATION_SCHEMA_VERSION


@dataclass(frozen=True)
class WebhookDestination:
    """Validated resolution result that a connector must use without re-resolution."""

    hostname: str
    port: int
    addresses: tuple[str, ...]


@dataclass(frozen=True, repr=False)
class WebhookRequest:
    """One bounded request whose representation omits body and credential material."""

    body: bytes
    headers: Mapping[str, str]
    bearer_material: SecretMaterial | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))

    def __repr__(self) -> str:
        return (
            f"WebhookRequest(body=<redacted:{len(self.body)} bytes>, "
            f"headers={tuple(self.headers)}, bearer_material=<redacted>)"
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


def parse_webhook_endpoints(
    values: Mapping[str, object], origin: str
) -> Mapping[str, WebhookEndpoint]:
    """Parse one versioned endpoint document into immutable typed endpoints."""

    unknown = set(values) - {"schema_version", "endpoints"}
    if unknown:
        raise ConfigurationError(f"Unknown webhook field '{sorted(unknown)[0]}' in {origin}.")
    if values.get("schema_version") != WEBHOOK_CONFIGURATION_SCHEMA_VERSION:
        raise ConfigurationError(
            f"Webhook schema_version in {origin} must be {WEBHOOK_CONFIGURATION_SCHEMA_VERSION}."
        )
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
        parsed[endpoint_id] = _parse_endpoint(endpoint_id, definition, origin)
    return MappingProxyType(parsed)


def resolve_webhook_destination(
    endpoint: WebhookEndpoint, resolver: WebhookAddressResolver
) -> WebhookDestination:
    """Resolve and reject any destination containing a non-global address."""

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
        if (
            not address.is_global
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_unspecified
            or address.is_reserved
            or address.is_private
        ):
            raise ConfigurationError("Webhook destination is denied by address policy.")
        canonical = str(address)
        if canonical not in addresses:
            addresses.append(canonical)
    return WebhookDestination(endpoint.hostname, endpoint.port, tuple(addresses))


def _parse_endpoint(endpoint_id: str, values: Mapping[str, object], origin: str) -> WebhookEndpoint:
    unknown = set(values) - _ENDPOINT_FIELDS
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
    bearer_secret = _parse_secret_reference(bearer_value, endpoint_id)
    connect_timeout = _positive_timeout(
        values.get("connect_timeout_seconds", 10), endpoint_id, "connect_timeout_seconds"
    )
    read_timeout = _positive_timeout(
        values.get("read_timeout_seconds", 30), endpoint_id, "read_timeout_seconds"
    )
    return WebhookEndpoint(
        endpoint_id,
        url,
        hostname,
        port,
        allowed,
        bearer_secret,
        connect_timeout,
        read_timeout,
    )


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


def _parse_secret_reference(value: object, endpoint_id: str) -> SecretReference | None:
    if value is None:
        return None
    if not isinstance(value, str) or value.count(":") != 1:
        raise ConfigurationError(
            f"Webhook endpoint '{endpoint_id}' bearer_secret must be a provider:key reference."
        )
    provider, key = value.split(":", 1)
    try:
        return SecretReference(provider, key)
    except Exception as error:
        raise ConfigurationError(
            f"Webhook endpoint '{endpoint_id}' bearer_secret must be a provider:key reference."
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


__all__ = [
    "MAX_WEBHOOK_PAYLOAD_BYTES",
    "MAX_WEBHOOK_TIMEOUT_SECONDS",
    "WEBHOOK_CONFIGURATION_SCHEMA_VERSION",
    "WebhookAddressResolver",
    "WebhookDestination",
    "WebhookEndpoint",
    "WebhookRequest",
    "WebhookTransport",
    "parse_webhook_endpoints",
    "resolve_webhook_destination",
]

"""Fail-closed named private-network policy contracts for HTTPS webhooks."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ansiblectl.domain.errors import ConfigurationError

WEBHOOK_NETWORK_POLICY_SCHEMA_VERSION = 1
MAX_WEBHOOK_NETWORK_POLICIES = 32
MAX_WEBHOOK_POLICY_CIDRS = 16
_POLICY_ID_PATTERN = re.compile(r"[a-z][a-z0-9._-]{0,127}")
_PRIVATE_BASE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
)

AllowedNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


@dataclass(frozen=True, repr=False)
class WebhookNetworkPolicy:
    """One immutable named policy whose representation omits trust details."""

    policy_id: str
    allowed_networks: tuple[AllowedNetwork, ...]
    schema_version: int = WEBHOOK_NETWORK_POLICY_SCHEMA_VERSION

    def __repr__(self) -> str:
        return "WebhookNetworkPolicy(policy_id=<redacted>, allowed_networks=<redacted>)"


def parse_webhook_network_policies(
    values: Mapping[str, object], origin: str
) -> Mapping[str, WebhookNetworkPolicy]:
    """Parse one bounded policy document into immutable canonical networks."""

    unknown = set(values) - {"schema_version", "policies"}
    if unknown:
        raise ConfigurationError(f"Unknown webhook network policy field in {origin}.")
    if values.get("schema_version") != WEBHOOK_NETWORK_POLICY_SCHEMA_VERSION:
        raise ConfigurationError(
            f"Webhook network policy schema_version in {origin} must be "
            f"{WEBHOOK_NETWORK_POLICY_SCHEMA_VERSION}."
        )
    definitions = values.get("policies")
    if not isinstance(definitions, dict):
        raise ConfigurationError(f"Webhook network policies in {origin} must be a mapping.")
    if len(definitions) > MAX_WEBHOOK_NETWORK_POLICIES:
        raise ConfigurationError(f"Webhook network policy count in {origin} exceeds the limit.")
    parsed: dict[str, WebhookNetworkPolicy] = {}
    for policy_id, definition in definitions.items():
        if not isinstance(policy_id, str) or _POLICY_ID_PATTERN.fullmatch(policy_id) is None:
            raise ConfigurationError(
                f"Webhook network policy identifier in {origin} is not canonical."
            )
        if not isinstance(definition, dict) or set(definition) != {"allowed_cidrs"}:
            raise ConfigurationError(f"Webhook network policy definition in {origin} is invalid.")
        parsed[policy_id] = WebhookNetworkPolicy(
            policy_id, _parse_allowed_networks(definition["allowed_cidrs"], origin)
        )
    return MappingProxyType(parsed)


def _parse_allowed_networks(value: object, origin: str) -> tuple[AllowedNetwork, ...]:
    if not isinstance(value, list) or not value or len(value) > MAX_WEBHOOK_POLICY_CIDRS:
        raise ConfigurationError(f"Webhook network policy CIDRs in {origin} are invalid.")
    networks: list[AllowedNetwork] = []
    for candidate in value:
        if not isinstance(candidate, str) or "/" not in candidate:
            raise ConfigurationError(f"Webhook network policy CIDR in {origin} is not canonical.")
        try:
            network = ipaddress.ip_network(candidate, strict=True)
        except ValueError as error:
            raise ConfigurationError(
                f"Webhook network policy CIDR in {origin} is not canonical."
            ) from error
        if str(network) != candidate or not _is_approved_private_network(network):
            raise ConfigurationError(f"Webhook network policy CIDR in {origin} is not allowed.")
        if any(network.overlaps(existing) for existing in networks):
            raise ConfigurationError(f"Webhook network policy CIDRs in {origin} overlap.")
        networks.append(network)
    return tuple(networks)


def _is_approved_private_network(network: AllowedNetwork) -> bool:
    if isinstance(network, ipaddress.IPv4Network):
        return any(
            isinstance(base, ipaddress.IPv4Network) and network.subnet_of(base)
            for base in _PRIVATE_BASE_NETWORKS
        )
    return any(
        isinstance(base, ipaddress.IPv6Network) and network.subnet_of(base)
        for base in _PRIVATE_BASE_NETWORKS
    )


__all__ = [
    "MAX_WEBHOOK_NETWORK_POLICIES",
    "MAX_WEBHOOK_POLICY_CIDRS",
    "WEBHOOK_NETWORK_POLICY_SCHEMA_VERSION",
    "WebhookNetworkPolicy",
    "parse_webhook_network_policies",
]

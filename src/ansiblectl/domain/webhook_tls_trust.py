"""Named exclusive TLS trust contracts for outbound webhooks."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from types import MappingProxyType

from ansiblectl.domain.errors import ConfigurationError

WEBHOOK_TLS_TRUST_SCHEMA_VERSION = 1
MAX_WEBHOOK_TLS_TRUST_POLICIES = 32
MAX_WEBHOOK_CA_CERTIFICATES = 16
_POLICY_ID_PATTERN = re.compile(r"[a-z][a-z0-9._-]{0,127}")
_PATH_COMPONENT_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")


@dataclass(frozen=True, repr=False)
class WebhookTlsTrustDefinition:
    policy_id: str
    ca_bundle_path: PurePosixPath

    def __repr__(self) -> str:
        return "WebhookTlsTrustDefinition(policy_id=<redacted>, ca_bundle_path=<redacted>)"


@dataclass(frozen=True, repr=False)
class WebhookTlsTrustPolicy:
    policy_id: str
    ca_pem: bytes
    schema_version: int = WEBHOOK_TLS_TRUST_SCHEMA_VERSION

    def __repr__(self) -> str:
        return "WebhookTlsTrustPolicy(policy_id=<redacted>, ca_pem=<redacted>)"


def parse_webhook_tls_trust_definitions(
    values: Mapping[str, object], origin: str
) -> Mapping[str, WebhookTlsTrustDefinition]:
    unknown = set(values) - {"schema_version", "policies"}
    if unknown:
        raise ConfigurationError(f"Unknown webhook TLS trust field in {origin}.")
    if values.get("schema_version") != WEBHOOK_TLS_TRUST_SCHEMA_VERSION:
        raise ConfigurationError(f"Webhook TLS trust schema_version in {origin} is unsupported.")
    definitions = values.get("policies")
    if not isinstance(definitions, dict):
        raise ConfigurationError(f"Webhook TLS trust policies in {origin} must be a mapping.")
    if len(definitions) > MAX_WEBHOOK_TLS_TRUST_POLICIES:
        raise ConfigurationError(f"Webhook TLS trust policy count in {origin} exceeds the limit.")
    parsed: dict[str, WebhookTlsTrustDefinition] = {}
    for policy_id, definition in definitions.items():
        if not isinstance(policy_id, str) or _POLICY_ID_PATTERN.fullmatch(policy_id) is None:
            raise ConfigurationError(f"Webhook TLS trust policy identifier in {origin} is invalid.")
        if not isinstance(definition, dict) or set(definition) != {"ca_bundle"}:
            raise ConfigurationError(f"Webhook TLS trust policy definition in {origin} is invalid.")
        parsed[policy_id] = WebhookTlsTrustDefinition(
            policy_id, _parse_bundle_path(definition["ca_bundle"], origin)
        )
    return MappingProxyType(parsed)


def _parse_bundle_path(value: object, origin: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 255:
        raise ConfigurationError(f"Webhook TLS CA bundle path in {origin} is invalid.")
    try:
        value.encode("ascii")
    except UnicodeEncodeError as error:
        raise ConfigurationError(f"Webhook TLS CA bundle path in {origin} is invalid.") from error
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or path.suffix != ".pem"
        or any(
            component in {"", ".", ".."} or _PATH_COMPONENT_PATTERN.fullmatch(component) is None
            for component in path.parts
        )
    ):
        raise ConfigurationError(f"Webhook TLS CA bundle path in {origin} is invalid.")
    return path


__all__ = [
    "MAX_WEBHOOK_CA_CERTIFICATES",
    "MAX_WEBHOOK_TLS_TRUST_POLICIES",
    "WEBHOOK_TLS_TRUST_SCHEMA_VERSION",
    "WebhookTlsTrustDefinition",
    "WebhookTlsTrustPolicy",
    "parse_webhook_tls_trust_definitions",
]

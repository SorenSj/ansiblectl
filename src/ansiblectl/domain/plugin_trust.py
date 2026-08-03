"""Typed, canonical contracts for detached plugin provenance."""

from __future__ import annotations

import base64
import binascii
import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from urllib.parse import urlsplit, urlunsplit

from ansiblectl.domain.errors import PluginError

MAX_PROVENANCE_BYTES = 16_384
PROVENANCE_DOMAIN = b"ansiblectl-plugin-provenance-v1\n"
_FIELDS = frozenset(
    {
        "schema_version",
        "provider_identity",
        "plugin_version",
        "sdk_compatibility",
        "artifact_digest",
        "origin",
        "signing_key_id",
        "signature",
    }
)
_IDENTITY = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_KEY_ID = re.compile(r"ed25519:sha256:[0-9a-f]{64}")
_LOCAL_ORIGIN = re.compile(r"local:[a-z0-9][a-z0-9._/-]{0,127}")


class PluginTrustReason(StrEnum):
    """Stable, redaction-safe plugin trust outcomes."""

    PROVENANCE_INVALID = "PROVENANCE_INVALID"
    SIGNING_KEY_UNTRUSTED = "SIGNING_KEY_UNTRUSTED"
    SIGNATURE_INVALID = "SIGNATURE_INVALID"
    ARTIFACT_DIGEST_MISMATCH = "ARTIFACT_DIGEST_MISMATCH"
    MANIFEST_PROVENANCE_MISMATCH = "MANIFEST_PROVENANCE_MISMATCH"
    ORIGIN_UNTRUSTED = "ORIGIN_UNTRUSTED"
    POLICY_REQUIRED = "POLICY_REQUIRED"
    POLICY_DENIED = "POLICY_DENIED"
    POLICY_AMBIGUOUS = "POLICY_AMBIGUOUS"
    PERMISSION_CEILING_EXCEEDED = "PERMISSION_CEILING_EXCEEDED"


class PluginTrustError(PluginError):
    """Reject plugin trust safely with one stable public reason."""

    def __init__(self, reason: PluginTrustReason) -> None:
        super().__init__(
            "Plugin trust verification failed.",
            hint="Verify the plugin artifact, provenance, signing key, and trust policy.",
            context={"reason": reason.value},
        )
        self.reason = reason


@dataclass(frozen=True)
class PluginProvenance:
    """Validated version 1 provenance statement."""

    provider_identity: str
    plugin_version: str
    sdk_compatibility: str
    artifact_digest: str
    origin: str
    signing_key_id: str
    signature: bytes
    schema_version: int = 1

    def signed_fields(self) -> Mapping[str, object]:
        """Return an immutable projection of exactly the signed fields."""

        return MappingProxyType(
            {
                "artifact_digest": self.artifact_digest,
                "origin": self.origin,
                "plugin_version": self.plugin_version,
                "provider_identity": self.provider_identity,
                "schema_version": self.schema_version,
                "sdk_compatibility": self.sdk_compatibility,
                "signing_key_id": self.signing_key_id,
            }
        )


@dataclass(frozen=True)
class PluginTrustDecision:
    """Complete redaction-safe public result of one trust evaluation."""

    provider_identity: str
    plugin_version: str
    artifact_digest: str
    signing_key_id: str
    origin: str
    requested_permissions: tuple[str, ...]
    granted_permissions: tuple[str, ...]
    denied_permissions: tuple[str, ...]
    trusted: bool
    reasons: tuple[PluginTrustReason, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        permissions = (
            self.requested_permissions,
            self.granted_permissions,
            self.denied_permissions,
        )
        if (
            self.schema_version != 1
            or not isinstance(self.trusted, bool)
            or not _IDENTITY.fullmatch(self.provider_identity)
            or not self.plugin_version
            or len(self.plugin_version) > 128
            or not _DIGEST.fullmatch(self.artifact_digest)
            or not _KEY_ID.fullmatch(self.signing_key_id)
            or _normalized_origin(self.origin) != self.origin
            or any(
                not isinstance(values, tuple)
                or tuple(sorted(set(values))) != values
                or any(not isinstance(value, str) or not value for value in values)
                for values in permissions
            )
            or not isinstance(self.reasons, tuple)
            or any(not isinstance(reason, PluginTrustReason) for reason in self.reasons)
        ):
            raise ValueError("Plugin trust decision fields must use the public canonical schema.")
        requested = set(self.requested_permissions)
        if self.trusted:
            valid_outcome = (
                not self.reasons
                and self.granted_permissions == self.requested_permissions
                and not self.denied_permissions
            )
        else:
            valid_outcome = (
                len(self.reasons) == 1
                and not self.granted_permissions
                and set(self.denied_permissions) == requested
            )
        if not valid_outcome:
            raise ValueError("Plugin trust decision outcome must be internally consistent.")

    @classmethod
    def allowed(
        cls, provenance: PluginProvenance, requested_permissions: tuple[str, ...]
    ) -> PluginTrustDecision:
        """Create a successful decision without retaining private inputs."""

        requested = tuple(sorted(set(requested_permissions)))
        return cls(
            provenance.provider_identity,
            provenance.plugin_version,
            provenance.artifact_digest,
            provenance.signing_key_id,
            provenance.origin,
            requested,
            requested,
            (),
            True,
        )

    @classmethod
    def denied(
        cls,
        provenance: PluginProvenance,
        requested_permissions: tuple[str, ...],
        reason: PluginTrustReason,
    ) -> PluginTrustDecision:
        """Create one fail-closed decision with the first stable reason only."""

        requested = tuple(sorted(set(requested_permissions)))
        return cls(
            provenance.provider_identity,
            provenance.plugin_version,
            provenance.artifact_digest,
            provenance.signing_key_id,
            provenance.origin,
            requested,
            (),
            requested,
            False,
            (reason,),
        )

    def to_payload(self) -> dict[str, object]:
        """Return the versioned JSON/YAML-safe contract."""

        return {
            "schema_version": self.schema_version,
            "provider_identity": self.provider_identity,
            "plugin_version": self.plugin_version,
            "artifact_digest": self.artifact_digest,
            "signing_key_id": self.signing_key_id,
            "origin": self.origin,
            "requested_permissions": list(self.requested_permissions),
            "granted_permissions": list(self.granted_permissions),
            "denied_permissions": list(self.denied_permissions),
            "trusted": self.trusted,
            "reasons": [reason.value for reason in self.reasons],
        }


def parse_provenance(data: bytes) -> PluginProvenance:
    """Parse bounded JSON and reject non-canonical or ambiguous fields."""

    if not data or len(data) > MAX_PROVENANCE_BYTES:
        raise PluginTrustError(PluginTrustReason.PROVENANCE_INVALID)
    try:
        values = json.loads(data, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise PluginTrustError(PluginTrustReason.PROVENANCE_INVALID) from error
    if not isinstance(values, dict) or set(values) != _FIELDS:
        raise PluginTrustError(PluginTrustReason.PROVENANCE_INVALID)
    if values["schema_version"] != 1 or isinstance(values["schema_version"], bool):
        raise PluginTrustError(PluginTrustReason.PROVENANCE_INVALID)
    strings = {name: _required_string(values, name) for name in _FIELDS - {"schema_version"}}
    if any(unicodedata.normalize("NFC", value) != value for value in strings.values()):
        raise PluginTrustError(PluginTrustReason.PROVENANCE_INVALID)
    if not _IDENTITY.fullmatch(strings["provider_identity"]):
        raise PluginTrustError(PluginTrustReason.PROVENANCE_INVALID)
    if len(strings["plugin_version"]) > 128 or len(strings["sdk_compatibility"]) > 128:
        raise PluginTrustError(PluginTrustReason.PROVENANCE_INVALID)
    if not _DIGEST.fullmatch(strings["artifact_digest"]):
        raise PluginTrustError(PluginTrustReason.PROVENANCE_INVALID)
    if not _KEY_ID.fullmatch(strings["signing_key_id"]):
        raise PluginTrustError(PluginTrustReason.PROVENANCE_INVALID)
    if _normalized_origin(strings["origin"]) != strings["origin"]:
        raise PluginTrustError(PluginTrustReason.PROVENANCE_INVALID)
    signature = _decode_signature(strings["signature"])
    return PluginProvenance(
        provider_identity=strings["provider_identity"],
        plugin_version=strings["plugin_version"],
        sdk_compatibility=strings["sdk_compatibility"],
        artifact_digest=strings["artifact_digest"],
        origin=strings["origin"],
        signing_key_id=strings["signing_key_id"],
        signature=signature,
    )


def canonical_payload(provenance: PluginProvenance) -> bytes:
    """Return the domain-separated canonical bytes covered by the signature."""

    encoded = json.dumps(
        dict(provenance.signed_fields()),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return PROVENANCE_DOMAIN + encoded


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    values: dict[str, object] = {}
    for name, value in pairs:
        if name in values:
            raise ValueError("duplicate JSON key")
        values[name] = value
    return values


def _required_string(values: Mapping[str, object], name: str) -> str:
    value = values[name]
    if not isinstance(value, str) or not value:
        raise PluginTrustError(PluginTrustReason.PROVENANCE_INVALID)
    return value


def _decode_signature(value: str) -> bytes:
    if "=" in value:
        raise PluginTrustError(PluginTrustReason.PROVENANCE_INVALID)
    try:
        signature = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, binascii.Error) as error:
        raise PluginTrustError(PluginTrustReason.PROVENANCE_INVALID) from error
    if len(signature) != 64 or base64.urlsafe_b64encode(signature).rstrip(b"=").decode() != value:
        raise PluginTrustError(PluginTrustReason.PROVENANCE_INVALID)
    return signature


def _normalized_origin(value: str) -> str | None:
    if _LOCAL_ORIGIN.fullmatch(value) and ".." not in value.split(":", 1)[1].split("/"):
        return value
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        return None
    hostname = parsed.hostname.lower()
    netloc = f"{hostname}:{port}" if port is not None else hostname
    path = parsed.path.rstrip("/")
    return urlunsplit(("https", netloc, path, "", ""))


__all__ = [
    "MAX_PROVENANCE_BYTES",
    "PROVENANCE_DOMAIN",
    "PluginProvenance",
    "PluginTrustDecision",
    "PluginTrustError",
    "PluginTrustReason",
    "canonical_payload",
    "parse_provenance",
]

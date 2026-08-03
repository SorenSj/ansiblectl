"""Typed configuration model and source port."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from ansiblectl.domain.errors import ConfigurationError

CONFIGURATION_SCHEMA_VERSION = 1
DEFAULT_LOG_LEVEL = "info"
_ALLOWED_FIELDS = {"schema_version", "project_name", "log_level", "secrets"}
_LOG_LEVELS = {"debug", "info", "warning", "error"}
_SECRET_REFERENCE = re.compile(r"^[a-z][a-z0-9_-]*:[^\s]+$")


@dataclass(frozen=True)
class ConfigurationSource:
    """A parsed configuration mapping tied to a diagnostic origin."""

    origin: str
    values: Mapping[str, object]


@dataclass(frozen=True)
class EffectiveConfiguration:
    """Validated settings and safe provenance, never secret material."""

    project_name: str | None
    log_level: str
    secret_references: Mapping[str, str]
    provenance: Mapping[str, str]

    def redacted(self) -> dict[str, object]:
        """Return the stable effective-configuration output contract."""

        return {
            "log_level": self.log_level,
            "project_name": self.project_name,
            "secrets": {name: "<redacted>" for name in self.secret_references},
            "provenance": dict(self.provenance),
        }


class ConfigurationSourceProvider(Protocol):
    """Port that supplies configuration sources in precedence order."""

    def sources(self) -> list[ConfigurationSource]:
        """Return all configured sources from lowest to highest precedence."""


def validate_configuration(values: Mapping[str, object], origin: str) -> dict[str, object]:
    """Validate one source document before it can affect effective settings."""

    unknown = set(values) - _ALLOWED_FIELDS
    if unknown:
        raise ConfigurationError(
            f"Unknown field '{sorted(unknown)[0]}' in {origin}. Remove it or correct its name."
        )
    if values.get("schema_version") != CONFIGURATION_SCHEMA_VERSION:
        raise ConfigurationError(
            f"Field 'schema_version' in {origin} must be {CONFIGURATION_SCHEMA_VERSION}."
        )
    project_name = values.get("project_name")
    if project_name is not None and (not isinstance(project_name, str) or not project_name.strip()):
        raise ConfigurationError(f"Field 'project_name' in {origin} must be a non-empty string.")
    log_level = values.get("log_level")
    if log_level is not None and log_level not in _LOG_LEVELS:
        raise ConfigurationError(
            f"Field 'log_level' in {origin} must be one of {sorted(_LOG_LEVELS)}."
        )
    secrets = values.get("secrets")
    if secrets is not None and (
        not isinstance(secrets, dict)
        or any(
            not isinstance(name, str)
            or not isinstance(reference, str)
            or not _SECRET_REFERENCE.fullmatch(reference)
            for name, reference in secrets.items()
        )
    ):
        raise ConfigurationError(
            f"Field 'secrets' in {origin} must map names to provider:key references."
        )
    return dict(values)


def make_effective_configuration(sources: list[ConfigurationSource]) -> EffectiveConfiguration:
    """Merge validated sources according to their declared low-to-high precedence."""

    merged: dict[str, object] = {"log_level": DEFAULT_LOG_LEVEL, "secrets": {}}
    provenance: dict[str, str] = {"log_level": "built-in defaults", "secrets": "built-in defaults"}
    for source in sources:
        for field, value in validate_configuration(source.values, source.origin).items():
            if field != "schema_version":
                merged[field] = value
                provenance[field] = source.origin
    secrets = merged["secrets"]
    assert isinstance(secrets, dict)
    project_name = merged.get("project_name")
    return EffectiveConfiguration(
        project_name=project_name if isinstance(project_name, str) else None,
        log_level=str(merged["log_level"]),
        secret_references=MappingProxyType(dict(secrets)),
        provenance=MappingProxyType(provenance),
    )

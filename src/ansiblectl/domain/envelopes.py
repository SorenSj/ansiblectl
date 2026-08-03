"""Versioned machine-readable command success and error envelopes."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Self

from ansiblectl.domain.context import CommandContext
from ansiblectl.domain.errors import AnsiblectlError, ValidationError
from ansiblectl.domain.results import CommandResult, CommandWarning

ENVELOPE_SCHEMA_VERSION = "1"
_ERROR_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
_ERROR_CATEGORY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class StructuredError:
    """Stable machine-readable representation of an expected failure."""

    code: str
    category: str
    message: str
    detail: str | None = None
    hint: str | None = None
    context: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not _ERROR_CODE_PATTERN.fullmatch(self.code):
            raise ValidationError("Structured error code must be a stable uppercase identifier.")
        if not isinstance(self.category, str) or not _ERROR_CATEGORY_PATTERN.fullmatch(
            self.category
        ):
            raise ValidationError(
                "Structured error category must be a stable lowercase identifier."
            )
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValidationError("Structured error message must be non-empty.")
        for name, value in (("detail", self.detail), ("hint", self.hint)):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValidationError(f"Structured error {name} must be non-empty when provided.")
        if not isinstance(self.context, Mapping) or not all(
            isinstance(name, str) for name in self.context
        ):
            raise ValidationError("Structured error context must be a string-keyed mapping.")
        object.__setattr__(self, "context", MappingProxyType(dict(self.context)))

    @classmethod
    def from_error(cls, error: AnsiblectlError) -> Self:
        """Create public error data without including the Python cause."""

        return cls(
            code=error.error_code.value,
            category=error.category,
            message=error.message,
            detail=error.detail,
            hint=error.hint,
            context=dict(error.context),
        )

    def to_payload(self) -> dict[str, object]:
        """Return the stable schema representation of this error."""

        return {
            "code": self.code,
            "category": self.category,
            "message": self.message,
            "detail": self.detail,
            "hint": self.hint,
            "context": dict(self.context),
        }


@dataclass(frozen=True)
class SuccessEnvelope[T]:
    """Versioned success envelope for JSON and YAML renderers."""

    operation_id: str
    command: str
    changed: bool
    data: T | None = None
    message: str | None = None
    warnings: tuple[CommandWarning, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)
    schema_version: str = ENVELOPE_SCHEMA_VERSION
    status: str = "success"

    def __post_init__(self) -> None:
        _validate_envelope_base(
            self.operation_id,
            self.command,
            self.changed,
            self.warnings,
            self.metadata,
            self.schema_version,
            self.status,
            expected_status="success",
        )
        if self.message is not None and (
            not isinstance(self.message, str) or not self.message.strip()
        ):
            raise ValidationError("Success envelope message must be non-empty when provided.")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @classmethod
    def from_result(cls, context: CommandContext, result: CommandResult[T]) -> SuccessEnvelope[T]:
        """Combine invocation context with an application result."""

        return cls(
            operation_id=context.operation_id,
            command=context.command_name,
            changed=result.changed,
            data=result.data,
            message=result.message,
            warnings=result.warnings,
            metadata=dict(result.metadata),
        )

    def to_payload(self) -> dict[str, object]:
        """Return the complete stable success schema."""

        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "operation_id": self.operation_id,
            "command": self.command,
            "changed": self.changed,
            "message": self.message,
            "data": self.data,
            "warnings": [_warning_payload(warning) for warning in self.warnings],
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ErrorEnvelope:
    """Versioned error envelope for JSON and YAML renderers."""

    operation_id: str
    command: str
    error: StructuredError
    warnings: tuple[CommandWarning, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)
    schema_version: str = ENVELOPE_SCHEMA_VERSION
    status: str = "error"
    changed: bool = False

    def __post_init__(self) -> None:
        _validate_envelope_base(
            self.operation_id,
            self.command,
            self.changed,
            self.warnings,
            self.metadata,
            self.schema_version,
            self.status,
            expected_status="error",
        )
        if not isinstance(self.error, StructuredError):
            raise ValidationError("Error envelope error must be a StructuredError value.")
        if self.changed is not False:
            raise ValidationError("Error envelope changed flag must be false.")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @classmethod
    def from_error(
        cls,
        context: CommandContext,
        error: AnsiblectlError,
        *,
        warnings: tuple[CommandWarning, ...] = (),
        metadata: Mapping[str, object] | None = None,
    ) -> Self:
        """Combine invocation context with a safe structured failure."""

        return cls(
            operation_id=context.operation_id,
            command=context.command_name,
            error=StructuredError.from_error(error),
            warnings=warnings,
            metadata=dict(metadata or {}),
        )

    def to_payload(self) -> dict[str, object]:
        """Return the complete stable error schema."""

        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "operation_id": self.operation_id,
            "command": self.command,
            "changed": self.changed,
            "error": self.error.to_payload(),
            "warnings": [_warning_payload(warning) for warning in self.warnings],
            "metadata": dict(self.metadata),
        }


def _warning_payload(warning: CommandWarning) -> dict[str, object]:
    return {
        "code": warning.code,
        "message": warning.message,
        "context": dict(warning.context),
    }


def _validate_envelope_base(
    operation_id: str,
    command: str,
    changed: bool,
    warnings: tuple[CommandWarning, ...],
    metadata: Mapping[str, object],
    schema_version: str,
    status: str,
    *,
    expected_status: str,
) -> None:
    CommandContext(operation_id, command, False, "text", False)
    if not isinstance(changed, bool):
        raise ValidationError("Envelope changed flag must be a boolean value.")
    if not isinstance(warnings, tuple) or not all(
        isinstance(warning, CommandWarning) for warning in warnings
    ):
        raise ValidationError("Envelope warnings must be a tuple of CommandWarning values.")
    if not isinstance(metadata, Mapping) or not all(isinstance(name, str) for name in metadata):
        raise ValidationError("Envelope metadata must be a string-keyed mapping.")
    if schema_version != ENVELOPE_SCHEMA_VERSION:
        raise ValidationError("Envelope schema version must match the public contract.")
    if status != expected_status:
        raise ValidationError("Envelope status must match its envelope type.")


__all__ = [
    "ENVELOPE_SCHEMA_VERSION",
    "ErrorEnvelope",
    "StructuredError",
    "SuccessEnvelope",
]

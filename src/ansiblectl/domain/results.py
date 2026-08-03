"""Structured success results shared across application and delivery layers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from ansiblectl.domain.errors import ValidationError

_WARNING_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


@dataclass(frozen=True)
class CommandWarning:
    """A stable, non-fatal issue associated with a successful command."""

    code: str
    message: str
    context: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not _WARNING_CODE_PATTERN.fullmatch(self.code):
            raise ValidationError("Command warning code must be a stable uppercase identifier.")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValidationError("Command warning message must be non-empty.")
        if not isinstance(self.context, Mapping):
            raise ValidationError("Command warning context must be a mapping.")
        object.__setattr__(self, "context", MappingProxyType(dict(self.context)))


@dataclass(frozen=True)
class CommandResult[T]:
    """A delivery-neutral result returned by an application command."""

    data: T | None = None
    message: str | None = None
    changed: bool = False
    warnings: tuple[CommandWarning, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.message is not None and (
            not isinstance(self.message, str) or not self.message.strip()
        ):
            raise ValidationError("Command result message must be non-empty when provided.")
        if not isinstance(self.changed, bool):
            raise ValidationError("Command result changed flag must be a boolean value.")
        if not isinstance(self.warnings, tuple) or not all(
            isinstance(warning, CommandWarning) for warning in self.warnings
        ):
            raise ValidationError(
                "Command result warnings must be a tuple of CommandWarning values."
            )
        if not isinstance(self.metadata, Mapping):
            raise ValidationError("Command result metadata must be a mapping.")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


__all__ = ["CommandResult", "CommandWarning"]

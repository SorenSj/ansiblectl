"""Render Phase 1 command envelopes for human and machine consumers."""

from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping
from enum import Enum
from typing import TextIO

import yaml

from ansiblectl.domain.context import CommandContext
from ansiblectl.domain.envelopes import ErrorEnvelope, SuccessEnvelope
from ansiblectl.domain.errors import AnsiblectlError, ExitCode
from ansiblectl.domain.redaction import redact
from ansiblectl.domain.results import CommandResult, CommandWarning


def render_success[T](
    context: CommandContext,
    result: CommandResult[T],
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Render one successful result and return the stable success exit code."""

    envelope = SuccessEnvelope.from_result(context, result)
    if context.output_format == "text":
        print(_terminal_safe(result.message or f"{context.command_name}: completed"), file=stdout)
        _render_text_warnings(result.warnings, stderr)
    else:
        _render_machine(envelope.to_payload(), context.output_format, stdout)
    return ExitCode.SUCCESS


def render_error(
    context: CommandContext,
    error: AnsiblectlError,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Render one safe failure and return its stable public exit code."""

    envelope = ErrorEnvelope.from_error(context, error)
    if context.output_format == "text":
        print(_human_error(envelope), file=stderr)
    else:
        _render_machine(envelope.to_payload(), context.output_format, stdout)
    return error.exit_code


def _render_machine(payload: Mapping[str, object], output_format: str, output: TextIO) -> None:
    safe_payload = _public_safe(redact(payload))
    if output_format == "json":
        print(json.dumps(safe_payload, sort_keys=True), file=output)
    elif output_format == "yaml":
        yaml.safe_dump(safe_payload, output, sort_keys=True)
    else:
        raise ValueError(f"Unsupported machine output format: {output_format}")


def _public_safe(value: object) -> object:
    """Normalize public data without invoking value-bearing object representations."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Enum):
        return _public_safe(value.value)
    if isinstance(value, os.PathLike):
        return _public_safe(os.fspath(value))
    if isinstance(value, Mapping):
        return {_public_key(name): _public_safe(item) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_public_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_public_safe(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True))
    return f"<unsupported:{value.__class__.__name__}>"


def _public_key(value: object) -> str:
    """Normalize a mapping key without invoking an arbitrary string conversion."""

    if isinstance(value, str):
        return value
    if isinstance(value, (bool, int, float)):
        return json.dumps(_public_safe(value))
    if isinstance(value, Enum):
        return _public_key(value.value)
    if isinstance(value, os.PathLike):
        return _public_key(os.fspath(value))
    return f"<unsupported:{value.__class__.__name__}>"


def _human_error(envelope: ErrorEnvelope) -> str:
    error = envelope.error
    sections = [f"Error: {_terminal_safe(error.message)}"]
    if error.detail:
        sections.append(_terminal_safe(error.detail))
    safe_context = _public_safe(redact(error.context))
    if isinstance(safe_context, Mapping) and safe_context:
        values = "\n".join(
            f"  {_terminal_safe(name)}: {_terminal_safe(str(safe_context[name]))}"
            for name in sorted(safe_context)
        )
        sections.append(f"Context:\n{values}")
    if error.hint:
        sections.append(f"Suggested action:\n  {_terminal_safe(error.hint)}")
    sections.extend(
        (
            f"Error code: {error.code}",
            f"Operation ID: {envelope.operation_id}",
        )
    )
    return "\n\n".join(sections)


def _render_text_warnings(warnings: tuple[CommandWarning, ...], stderr: TextIO) -> None:
    for warning in warnings:
        print(f"Warning [{warning.code}]: {_terminal_safe(warning.message)}", file=stderr)


def _terminal_safe(value: str) -> str:
    """Render terminal control characters as visible, non-executable escapes."""

    return "".join(
        f"\\x{code:02x}" if code < 32 or 127 <= code <= 159 else character
        for character in value
        for code in (ord(character),)
    )


__all__ = ["render_error", "render_success"]

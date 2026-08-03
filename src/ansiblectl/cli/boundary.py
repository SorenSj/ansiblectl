"""Global exception boundary for Phase 1 application commands."""

from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import TextIO

from ansiblectl.cli.rendering import render_error, render_success
from ansiblectl.domain.context import CommandContext
from ansiblectl.domain.errors import (
    AnsiblectlError,
    InternalOperationalError,
    OperationCancelledError,
)
from ansiblectl.domain.results import CommandResult


def execute_command[T](
    context: CommandContext,
    callback: Callable[[], CommandResult[T]],
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Execute and render one callback behind the unified exception boundary."""

    try:
        result = callback()
        return render_success(context, result, stdout, stderr)
    except KeyboardInterrupt as cause:
        return render_exception(context, cause, stdout, stderr)
    except AnsiblectlError as cause:
        return render_exception(context, cause, stdout, stderr)
    except Exception as cause:
        return render_exception(context, cause, stdout, stderr)


def render_exception(
    context: CommandContext,
    cause: BaseException,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Classify and render one exception caught by a delivery entrypoint."""

    if isinstance(cause, KeyboardInterrupt):
        error: AnsiblectlError = OperationCancelledError(
            "The operation was cancelled by the user.",
            cause=cause,
        )
    elif isinstance(cause, AnsiblectlError):
        error = cause
    elif isinstance(cause, Exception):
        error = InternalOperationalError(
            "An unexpected internal error occurred.",
            hint="Run the command again with --debug and report the operation ID.",
            cause=cause,
        )
    else:
        raise cause

    exit_code = render_error(context, error, stdout, stderr)
    if context.debug:
        print(_debug_diagnostics(error), file=stderr)
    return exit_code


def _debug_diagnostics(error: AnsiblectlError) -> str:
    """Return value-free exception diagnostics that cannot reveal exception messages."""

    cause = error.cause
    if cause is None:
        return f"Debug diagnostics:\n  Error type: {error.__class__.__name__}"

    sections = [
        "Debug diagnostics:",
        f"  Error type: {error.__class__.__name__}",
        f"  Cause type: {cause.__class__.__name__}",
    ]
    frames = traceback.extract_tb(cause.__traceback__)
    if frames:
        sections.append("  Traceback frames:")
        sections.extend(f"    {frame.name}:{frame.lineno}" for frame in frames)
    return "\n".join(sections)


__all__ = ["execute_command", "render_exception"]

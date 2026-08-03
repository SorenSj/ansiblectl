"""Contract tests for the unified command exception boundary."""

import json
from io import StringIO

from ansiblectl.cli.boundary import execute_command
from ansiblectl.domain.context import CommandContext
from ansiblectl.domain.errors import ConflictError, ExitCode
from ansiblectl.domain.results import CommandResult

_OPERATION_ID = "00000000Z80000000000000000"


def _context(*, output_format: str = "json", debug: bool = False) -> CommandContext:
    return CommandContext(_OPERATION_ID, "repository create", debug, output_format, False)


def test_boundary_renders_successful_callback_result() -> None:
    stdout, stderr = StringIO(), StringIO()

    exit_code = execute_command(
        _context(),
        lambda: CommandResult(data={"repository": "automation"}, changed=True),
        stdout,
        stderr,
    )

    assert exit_code == ExitCode.SUCCESS
    assert json.loads(stdout.getvalue())["status"] == "success"
    assert stderr.getvalue() == ""


def test_boundary_maps_expected_error_without_losing_public_contract() -> None:
    stdout, stderr = StringIO(), StringIO()

    def fail() -> CommandResult[None]:
        raise ConflictError("Repository already exists.")

    exit_code = execute_command(_context(), fail, stdout, stderr)

    payload = json.loads(stdout.getvalue())
    assert exit_code == ExitCode.RESOURCE_CONFLICT
    assert payload["error"]["code"] == "CONFLICT"
    assert payload["error"]["message"] == "Repository already exists."
    assert stderr.getvalue() == ""


def test_boundary_hides_unexpected_exception_details_by_default() -> None:
    stdout, stderr = StringIO(), StringIO()

    def fail() -> CommandResult[None]:
        raise RuntimeError("github_token=do-not-expose")

    exit_code = execute_command(_context(), fail, stdout, stderr)

    rendered = stdout.getvalue()
    payload = json.loads(rendered)
    assert exit_code == ExitCode.GENERAL_ERROR
    assert payload["error"]["code"] == "INTERNAL_ERROR"
    assert payload["error"]["message"] == "An unexpected internal error occurred."
    assert "do-not-expose" not in rendered
    assert "RuntimeError" not in rendered
    assert stderr.getvalue() == ""


def test_boundary_maps_keyboard_interrupt_to_standard_cancellation() -> None:
    stdout, stderr = StringIO(), StringIO()

    def interrupt() -> CommandResult[None]:
        raise KeyboardInterrupt

    exit_code = execute_command(_context(), interrupt, stdout, stderr)

    payload = json.loads(stdout.getvalue())
    assert exit_code == ExitCode.INTERRUPTED
    assert payload["error"]["code"] == "OPERATION_CANCELLED"
    assert stderr.getvalue() == ""


def test_debug_mode_reports_types_and_frames_but_not_exception_values() -> None:
    stdout, stderr = StringIO(), StringIO()

    def fail_with_secret() -> CommandResult[None]:
        raise RuntimeError("password=do-not-expose")

    exit_code = execute_command(_context(debug=True), fail_with_secret, stdout, stderr)

    diagnostics = stderr.getvalue()
    assert exit_code == ExitCode.GENERAL_ERROR
    assert json.loads(stdout.getvalue())["status"] == "error"
    assert "Error type: InternalOperationalError" in diagnostics
    assert "Cause type: RuntimeError" in diagnostics
    assert "fail_with_secret:" in diagnostics
    assert "do-not-expose" not in diagnostics
    assert "password" not in diagnostics


def test_debug_mode_handles_expected_errors_without_a_cause() -> None:
    stdout, stderr = StringIO(), StringIO()

    def fail() -> CommandResult[None]:
        raise ConflictError("Conflict.")

    execute_command(_context(output_format="text", debug=True), fail, stdout, stderr)

    assert "Error type: ConflictError" in stderr.getvalue()

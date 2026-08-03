"""Contract tests for Phase 1 command rendering."""

import json
import math
from io import StringIO
from pathlib import Path

import yaml

from ansiblectl.cli.rendering import render_error, render_success
from ansiblectl.domain.context import CommandContext
from ansiblectl.domain.errors import ConflictError, ExitCode
from ansiblectl.domain.results import CommandResult, CommandWarning

_OPERATION_ID = "00000000Z80000000000000000"


def _context(output_format: str) -> CommandContext:
    return CommandContext(_OPERATION_ID, "repository create", False, output_format, False)


def test_json_success_is_one_redacted_document_on_stdout() -> None:
    stdout, stderr = StringIO(), StringIO()
    result = CommandResult(
        data={"repository": "automation", "github_token": "hidden"},
        message="Repository created.",
        changed=True,
    )

    exit_code = render_success(_context("json"), result, stdout, stderr)

    payload = json.loads(stdout.getvalue())
    assert exit_code == ExitCode.SUCCESS
    assert stderr.getvalue() == ""
    assert payload["status"] == "success"
    assert payload["data"]["github_token"] == "<redacted>"


def test_yaml_error_is_one_parseable_document_on_stdout() -> None:
    stdout, stderr = StringIO(), StringIO()
    error = ConflictError(
        "Repository already exists.",
        context={"path": "/srv/automation", "credential": "hidden"},
    )

    exit_code = render_error(_context("yaml"), error, stdout, stderr)

    payload = yaml.safe_load(stdout.getvalue())
    assert exit_code == ExitCode.RESOURCE_CONFLICT
    assert stderr.getvalue() == ""
    assert payload["status"] == "error"
    assert payload["error"]["context"]["credential"] == "<redacted>"


def test_text_error_is_actionable_and_writes_only_to_stderr() -> None:
    stdout, stderr = StringIO(), StringIO()
    error = ConflictError(
        "Repository already exists.",
        detail="The destination is not empty.",
        hint="Choose another destination.",
        context={"path": "/srv/automation", "token": "hidden"},
    )

    exit_code = render_error(_context("text"), error, stdout, stderr)

    assert exit_code == ExitCode.RESOURCE_CONFLICT
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == (
        "Error: Repository already exists.\n\n"
        "The destination is not empty.\n\n"
        "Context:\n"
        "  path: /srv/automation\n"
        "  token: <redacted>\n\n"
        "Suggested action:\n"
        "  Choose another destination.\n\n"
        "Error code: CONFLICT\n\n"
        f"Operation ID: {_OPERATION_ID}\n"
    )


def test_text_success_sends_warnings_to_stderr() -> None:
    stdout, stderr = StringIO(), StringIO()
    result = CommandResult[None](
        message="Repository inspected.",
        warnings=(CommandWarning("DIRTY_WORKTREE", "Uncommitted changes were found."),),
    )

    exit_code = render_success(_context("text"), result, stdout, stderr)

    assert exit_code == ExitCode.SUCCESS
    assert stdout.getvalue() == "Repository inspected.\n"
    assert stderr.getvalue() == "Warning [DIRTY_WORKTREE]: Uncommitted changes were found.\n"


def test_machine_renderer_normalizes_common_non_json_values() -> None:
    stdout, stderr = StringIO(), StringIO()
    result = CommandResult(
        data={
            "path": Path("automation/site.yml"),
            "exit_code": ExitCode.SUCCESS,
            "targets": {"web", "database"},
            "elapsed": math.inf,
        }
    )

    exit_code = render_success(_context("json"), result, stdout, stderr)

    payload = json.loads(stdout.getvalue())
    assert exit_code == ExitCode.SUCCESS
    assert stderr.getvalue() == ""
    assert payload["data"] == {
        "elapsed": None,
        "exit_code": 0,
        "path": "automation/site.yml",
        "targets": ["database", "web"],
    }


def test_machine_renderer_never_invokes_unknown_object_representation() -> None:
    class SensitiveObject:
        def __repr__(self) -> str:
            return "token=do-not-expose"

    stdout, stderr = StringIO(), StringIO()
    error = ConflictError("Conflict.", context={"adapter": SensitiveObject()})

    exit_code = render_error(_context("yaml"), error, stdout, stderr)

    payload = yaml.safe_load(stdout.getvalue())
    assert exit_code == ExitCode.RESOURCE_CONFLICT
    assert stderr.getvalue() == ""
    assert "do-not-expose" not in stdout.getvalue()
    assert payload["error"]["context"]["adapter"] == "<unsupported:SensitiveObject>"


def test_text_renderer_never_invokes_unknown_object_string_conversion() -> None:
    class SensitiveObject:
        def __str__(self) -> str:
            return "password=do-not-expose"

    stdout, stderr = StringIO(), StringIO()
    error = ConflictError("Conflict.", context={"adapter": SensitiveObject()})

    exit_code = render_error(_context("text"), error, stdout, stderr)

    assert exit_code == ExitCode.RESOURCE_CONFLICT
    assert stdout.getvalue() == ""
    assert "do-not-expose" not in stderr.getvalue()
    assert "adapter: <unsupported:SensitiveObject>" in stderr.getvalue()


def test_text_renderer_escapes_terminal_control_characters() -> None:
    stdout, stderr = StringIO(), StringIO()
    error = ConflictError(
        "Conflict.\x1b[2J",
        detail="Unsafe\rdetail",
        hint="Retry\tnow.",
        context={"path\x07": "value\x00"},
    )

    exit_code = render_error(_context("text"), error, stdout, stderr)

    rendered = stderr.getvalue()
    assert exit_code == ExitCode.RESOURCE_CONFLICT
    assert stdout.getvalue() == ""
    assert "\x1b" not in rendered
    assert "\x00" not in rendered
    assert "Conflict.\\x1b[2J" in rendered
    assert "Unsafe\\x0ddetail" in rendered
    assert "Retry\\x09now." in rendered
    assert "path\\x07: value\\x00" in rendered


def test_text_success_and_warning_escape_terminal_controls() -> None:
    stdout, stderr = StringIO(), StringIO()
    result = CommandResult[None](
        message="Complete.\x1b[31m",
        warnings=(CommandWarning("NOTICE", "Review\rresult."),),
    )

    exit_code = render_success(_context("text"), result, stdout, stderr)

    assert exit_code == ExitCode.SUCCESS
    assert stdout.getvalue() == "Complete.\\x1b[31m\n"
    assert stderr.getvalue() == "Warning [NOTICE]: Review\\x0dresult.\n"

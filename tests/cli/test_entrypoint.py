"""Installed CLI failure-boundary tests."""

import json
from io import StringIO
from pathlib import Path

import pytest
import yaml

from ansiblectl.cli.main import (
    EXIT_INVALID_INPUT,
    EXIT_UNEXPECTED_FAILURE,
    _legacy_error_for_command,
    _legacy_result_changed,
    _legacy_result_warnings,
    _requested_command_name,
    cli,
)
from ansiblectl.domain.errors import ErrorCode, ExitCode, WorkspaceNotFoundError


@pytest.mark.parametrize(
    ("command_name", "error_code", "exit_code"),
    [
        ("config show", ErrorCode.CONFIGURATION_ERROR, ExitCode.CONFIGURATION_ERROR),
        ("inventory show", ErrorCode.INVENTORY_ERROR, ExitCode.VALIDATION_ERROR),
        ("repository sync", ErrorCode.REPOSITORY_ERROR, ExitCode.RESOURCE_CONFLICT),
        ("plugin discover", ErrorCode.PLUGIN_ERROR, ExitCode.PLUGIN_ERROR),
        ("playbook validate", ErrorCode.PLAYBOOK_VALIDATION_FAILED, ExitCode.VALIDATION_ERROR),
        ("state show", ErrorCode.STATE_ERROR, ExitCode.RESOURCE_CONFLICT),
        ("workspace show", ErrorCode.WORKSPACE_ERROR, ExitCode.VALIDATION_ERROR),
        ("run", ErrorCode.EXECUTION_ERROR, ExitCode.EXTERNAL_TOOL_ERROR),
    ],
)
def test_legacy_failure_adapter_uses_stable_command_subsystem(
    command_name: str, error_code: ErrorCode, exit_code: ExitCode
) -> None:
    error = _legacy_error_for_command(command_name, "Safe failure.", "Retry safely.")

    assert error.error_code is error_code
    assert error.exit_code is exit_code
    assert error.message == "Safe failure."
    assert error.hint == "Retry safely."


@pytest.mark.parametrize(
    ("command_name", "payload", "changed"),
    [
        ("status", {"changed": True}, True),
        ("state invalidate", {"applied": True, "existed": True}, True),
        ("state invalidate", {"applied": False, "existed": True}, False),
        ("state invalidate", {"applied": True, "existed": False}, False),
        ("state recover", {"applied": True, "transaction_ids": ["one"]}, True),
        ("state recover", {"applied": False, "transaction_ids": ["one"]}, False),
        ("state recover", {"applied": True, "transaction_ids": []}, False),
        ("execution prune", {"applied": True, "removed_execution_ids": ["run-1"]}, True),
        ("execution prune", {"applied": True, "removed_execution_ids": []}, False),
        ("repository sync", {"resolved_revision": "abc123"}, False),
        ("status", ["not", "a", "mapping"], False),
    ],
)
def test_legacy_changed_inference_is_explicit_and_conservative(
    command_name: str, payload: object, changed: bool
) -> None:
    assert _legacy_result_changed(command_name, payload) is changed


@pytest.mark.parametrize(
    ("command", "payload"),
    [
        ("state invalidate", {"applied": True, "existed": True}),
        ("state recover", {"applied": True, "transaction_ids": ["one"]}),
        ("execution prune", {"applied": True, "removed_execution_ids": ["run-1"]}),
    ],
)
def test_entrypoint_preserves_explicit_legacy_change_state(
    monkeypatch: pytest.MonkeyPatch, command: str, payload: dict[str, object]
) -> None:
    stdout, stderr = StringIO(), StringIO()

    def succeed(*args: object, **kwargs: object) -> int:
        output = kwargs["stdout"]
        assert isinstance(output, StringIO)
        output.write(json.dumps(payload))
        return 0

    monkeypatch.setattr("ansiblectl.cli.main.main", succeed)

    result = cli(["--output", "json", *command.split()], stdout=stdout, stderr=stderr)

    envelope = json.loads(stdout.getvalue())
    assert result == 0
    assert stderr.getvalue() == ""
    assert envelope["changed"] is True


def test_recovery_corrupt_journal_uses_stable_public_error(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    assert cli(["workspace", "init", str(workspace)], stdout=StringIO()) == 0
    journal = workspace / ".ansiblectl/transactions/broken/journal.json"
    journal.parent.mkdir(parents=True)
    journal.write_text("not-json", encoding="utf-8")
    stdout, stderr = StringIO(), StringIO()

    result = cli(
        ["--workspace", str(workspace), "--output", "json", "state", "recover"],
        stdout=stdout,
        stderr=stderr,
    )

    assert result == ExitCode.RESOURCE_CONFLICT
    assert stderr.getvalue() == ""
    envelope = json.loads(stdout.getvalue())
    assert envelope["error"]["code"] == ErrorCode.FILESYSTEM_RECOVERY_REQUIRED
    assert journal.exists()


@pytest.mark.parametrize(
    ("command_name", "payload", "warning_code"),
    [
        (
            "inventory show",
            {"diagnostics": ["Host pattern used a compatibility fallback."]},
            "INVENTORY_DIAGNOSTIC",
        ),
        (
            "playbook validate",
            {"findings": ["Collection qualification is recommended."]},
            "PLAYBOOK_FINDING",
        ),
    ],
)
def test_legacy_warning_inference_uses_explicit_structured_findings(
    command_name: str, payload: dict[str, object], warning_code: str
) -> None:
    warnings = _legacy_result_warnings(command_name, payload)

    assert len(warnings) == 1
    assert warnings[0].code == warning_code


@pytest.mark.parametrize(
    ("command_name", "payload"),
    [
        ("inventory show", {"diagnostics": "not-a-list"}),
        ("inventory show", {"diagnostics": ["", 1, None]}),
        ("status", {"diagnostics": ["Not a supported warning source."]}),
        ("inventory show", ["not", "a", "mapping"]),
    ],
)
def test_legacy_warning_inference_ignores_ambiguous_values(
    command_name: str, payload: object
) -> None:
    assert _legacy_result_warnings(command_name, payload) == ()


def test_entrypoint_lifts_legacy_findings_into_success_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout, stderr = StringIO(), StringIO()

    def succeed(*args: object, **kwargs: object) -> int:
        output = kwargs["stdout"]
        assert isinstance(output, StringIO)
        output.write(json.dumps({"diagnostics": ["Compatibility fallback used."]}))
        return 0

    monkeypatch.setattr("ansiblectl.cli.main.main", succeed)

    result = cli(["--output", "json", "inventory", "show"], stdout=stdout, stderr=stderr)

    envelope = json.loads(stdout.getvalue())
    assert result == 0
    assert stderr.getvalue() == ""
    assert envelope["warnings"] == [
        {
            "code": "INVENTORY_DIAGNOSTIC",
            "context": {},
            "message": "Compatibility fallback used.",
        }
    ]


@pytest.mark.parametrize(
    ("arguments", "command_name"),
    [
        (("status",), "status"),
        (("--workspace", "status", "repository", "sync", "private"), "repository sync"),
        (("--output=json", "workspace", "init", "/private/path"), "workspace init"),
        (("--unknown", "private-value"), "ansiblectl"),
    ],
)
def test_command_identity_contains_only_documented_command_tokens(
    arguments: tuple[str, ...], command_name: str
) -> None:
    assert _requested_command_name(arguments) == command_name


def test_phase_output_json_wraps_legacy_command_data_in_success_envelope() -> None:
    stdout, stderr = StringIO(), StringIO()

    result = cli(["--output", "json", "status"], stdout=stdout, stderr=stderr)

    payload = json.loads(stdout.getvalue())
    assert result == 0
    assert stderr.getvalue() == ""
    assert payload["schema_version"] == "1"
    assert payload["status"] == "success"
    assert payload["command"] == "status"
    assert payload["changed"] is False
    assert payload["data"]["message"] == "Ansiblectl is ready."


def test_phase_output_yaml_emits_one_parseable_success_document() -> None:
    stdout, stderr = StringIO(), StringIO()

    result = cli(["--output=yaml", "status"], stdout=stdout, stderr=stderr)

    payload = yaml.safe_load(stdout.getvalue())
    assert result == 0
    assert stderr.getvalue() == ""
    assert payload["status"] == "success"
    assert payload["data"]["message"] == "Ansiblectl is ready."


@pytest.mark.parametrize(
    "arguments",
    [
        ["--output", "json", "--output-format", "human", "status"],
        ["--output-format=human", "--output=json", "status"],
    ],
)
def test_phase_output_takes_precedence_over_deprecated_option(
    arguments: list[str],
) -> None:
    stdout, stderr = StringIO(), StringIO()

    result = cli(arguments, stdout=stdout, stderr=stderr)

    payload = json.loads(stdout.getvalue())
    assert result == 0
    assert stderr.getvalue() == ""
    assert payload["status"] == "success"
    assert payload["command"] == "status"


@pytest.mark.parametrize("output_format", ["json", "yaml"])
def test_machine_output_discards_unstructured_legacy_diagnostics(
    monkeypatch: pytest.MonkeyPatch, output_format: str
) -> None:
    stdout, stderr = StringIO(), StringIO()

    def render_with_diagnostic(*args: object, **kwargs: object) -> int:
        output = kwargs["stdout"]
        diagnostic_output = kwargs["stderr"]
        assert isinstance(output, StringIO)
        assert isinstance(diagnostic_output, StringIO)
        output.write('{"message":"Safe result."}\n')
        diagnostic_output.write("token=do-not-expose\n")
        return 0

    monkeypatch.setattr("ansiblectl.cli.main.main", render_with_diagnostic)

    result = cli(["--output", output_format, "status"], stdout=stdout, stderr=stderr)

    payload = (
        json.loads(stdout.getvalue())
        if output_format == "json"
        else yaml.safe_load(stdout.getvalue())
    )
    assert result == 0
    assert stderr.getvalue() == ""
    assert "do-not-expose" not in stdout.getvalue()
    assert payload["data"] == {"message": "Safe result."}


def test_text_output_preserves_legacy_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout, stderr = StringIO(), StringIO()

    def render_with_diagnostic(*args: object, **kwargs: object) -> int:
        output = kwargs["stdout"]
        diagnostic_output = kwargs["stderr"]
        assert isinstance(output, StringIO)
        assert isinstance(diagnostic_output, StringIO)
        output.write("Safe result.\n")
        diagnostic_output.write("Progress diagnostic.\n")
        return 0

    monkeypatch.setattr("ansiblectl.cli.main.main", render_with_diagnostic)

    result = cli(["--output", "text", "status"], stdout=stdout, stderr=stderr)

    assert result == 0
    assert stdout.getvalue() == "Safe result.\n"
    assert stderr.getvalue() == "Progress diagnostic.\n"


def test_phase_text_output_takes_precedence_over_deprecated_json() -> None:
    stdout, stderr = StringIO(), StringIO()

    result = cli(
        ["--output-format=json", "--output", "text", "status"],
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert stderr.getvalue() == ""
    assert stdout.getvalue().startswith("ansiblectl ")


@pytest.mark.parametrize("output_format", ["json", "yaml"])
def test_entrypoint_contains_malformed_legacy_machine_output(
    monkeypatch: pytest.MonkeyPatch, output_format: str
) -> None:
    stdout, stderr = StringIO(), StringIO()

    def render_malformed(*args: object, **kwargs: object) -> int:
        output = kwargs["stdout"]
        assert isinstance(output, StringIO)
        output.write('{"token":"do-not-expose"')
        return 0

    monkeypatch.setattr("ansiblectl.cli.main.main", render_malformed)

    result = cli(["--output", output_format, "status"], stdout=stdout, stderr=stderr)

    payload = (
        json.loads(stdout.getvalue())
        if output_format == "json"
        else yaml.safe_load(stdout.getvalue())
    )
    assert result == EXIT_UNEXPECTED_FAILURE
    assert stderr.getvalue() == ""
    assert "do-not-expose" not in stdout.getvalue()
    assert payload["status"] == "error"
    assert payload["command"] == "status"
    assert payload["error"]["code"] == "INTERNAL_ERROR"


def test_output_environment_selects_machine_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout, stderr = StringIO(), StringIO()
    monkeypatch.setenv("ANSIBLECTL_OUTPUT", "json")

    result = cli(["status"], stdout=stdout, stderr=stderr)

    assert result == 0
    assert json.loads(stdout.getvalue())["status"] == "success"
    assert stderr.getvalue() == ""


def test_invalid_phase_output_does_not_execute_the_command() -> None:
    stdout, stderr = StringIO(), StringIO()

    result = cli(["--output", "xml", "status"], stdout=stdout, stderr=stderr)

    assert result == 2
    assert stdout.getvalue() == ""
    assert "Invalid output format." in stderr.getvalue()
    assert "Choose one of: text, json, or yaml." in stderr.getvalue()


def test_invalid_phase_output_does_not_echo_rejected_value() -> None:
    stdout, stderr = StringIO(), StringIO()

    result = cli(["--output=token-do-not-expose", "status"], stdout=stdout, stderr=stderr)

    assert result == EXIT_INVALID_INPUT
    assert "token-do-not-expose" not in stdout.getvalue() + stderr.getvalue()
    assert "source: command_line" in stderr.getvalue()


def test_missing_phase_output_value_is_a_usage_error() -> None:
    stdout, stderr = StringIO(), StringIO()

    result = cli(["status", "--output"], stdout=stdout, stderr=stderr)

    assert result == EXIT_INVALID_INPUT
    assert stdout.getvalue() == ""
    assert "Invalid output format." in stderr.getvalue()


def test_invalid_output_environment_fails_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout, stderr = StringIO(), StringIO()
    monkeypatch.setenv("ANSIBLECTL_OUTPUT", "token-do-not-expose")

    result = cli(["status"], stdout=stdout, stderr=stderr)

    assert result == EXIT_INVALID_INPUT
    assert stdout.getvalue() == ""
    assert "Invalid output format." in stderr.getvalue()
    assert "source: environment" in stderr.getvalue()
    assert "token-do-not-expose" not in stderr.getvalue()


def test_command_identity_excludes_global_option_values() -> None:
    stdout, stderr = StringIO(), StringIO()

    result = cli(
        ["--output", "json", "--workspace", "/private/sensitive/path", "status"],
        stdout=stdout,
        stderr=stderr,
    )

    payload = json.loads(stdout.getvalue())
    assert result == 0
    assert payload["command"] == "status"
    assert "/private/sensitive/path" not in stdout.getvalue()


@pytest.mark.parametrize(
    ("format_arguments", "output_format"),
    [
        ([], "human"),
        (["--output-format", "json"], "json"),
        (["--output-format=json"], "json"),
    ],
)
def test_entrypoint_maps_unexpected_failure_without_exposing_exception(
    monkeypatch: pytest.MonkeyPatch,
    format_arguments: list[str],
    output_format: str,
) -> None:
    stdout, stderr = StringIO(), StringIO()

    def fail(*args: object, **kwargs: object) -> int:
        raise RuntimeError("sensitive adapter detail")

    monkeypatch.setattr("ansiblectl.cli.main.main", fail)

    result = cli([*format_arguments, "status"], stdout=stdout, stderr=stderr)

    assert result == EXIT_UNEXPECTED_FAILURE == 1
    assert "sensitive adapter detail" not in stdout.getvalue() + stderr.getvalue()
    if output_format == "json":
        assert stderr.getvalue() == ""
        payload = json.loads(stdout.getvalue())
        assert payload["schema_version"] == "1"
        assert payload["status"] == "error"
        assert payload["command"] == "status"
        assert payload["changed"] is False
        assert payload["error"] == {
            "category": "internal",
            "code": "INTERNAL_ERROR",
            "context": {},
            "detail": None,
            "hint": "Run the command again with --debug and report the operation ID.",
            "message": "An unexpected internal error occurred.",
        }
        assert len(payload["operation_id"]) == 26
        assert payload["warnings"] == []
        assert payload["metadata"] == {}
    else:
        assert stdout.getvalue() == ""
        assert "An unexpected internal error occurred." in stderr.getvalue()


def test_entrypoint_maps_keyboard_interrupt_to_standard_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def interrupt(*args: object, **kwargs: object) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr("ansiblectl.cli.main.main", interrupt)

    stdout, stderr = StringIO(), StringIO()
    result = cli(["status"], stdout=stdout, stderr=stderr)

    assert result == 130
    assert stdout.getvalue() == ""
    assert "The operation was cancelled by the user." in stderr.getvalue()
    assert "Error code: OPERATION_CANCELLED" in stderr.getvalue()


@pytest.mark.parametrize("output_format", ["text", "json", "yaml"])
def test_entrypoint_translates_legacy_cancelled_result_atomically(
    monkeypatch: pytest.MonkeyPatch, output_format: str
) -> None:
    stdout, stderr = StringIO(), StringIO()

    def cancel(*args: object, **kwargs: object) -> int:
        output = kwargs["stdout"]
        assert isinstance(output, StringIO)
        output.write('{"token":"do-not-expose","status":"cancelled"}\n')
        return 3

    monkeypatch.setattr("ansiblectl.cli.main.main", cancel)

    result = cli(["--output", output_format, "run"], stdout=stdout, stderr=stderr)

    rendered = stdout.getvalue() + stderr.getvalue()
    assert result == ExitCode.INTERRUPTED
    assert "do-not-expose" not in rendered
    if output_format == "text":
        assert stdout.getvalue() == ""
        assert "Error code: OPERATION_CANCELLED" in stderr.getvalue()
    else:
        assert stderr.getvalue() == ""
        payload = (
            json.loads(stdout.getvalue())
            if output_format == "json"
            else yaml.safe_load(stdout.getvalue())
        )
        assert payload["status"] == "error"
        assert payload["error"]["code"] == "OPERATION_CANCELLED"


@pytest.mark.parametrize("output_format", ["text", "json", "yaml"])
@pytest.mark.parametrize(
    ("run_arguments", "message"),
    [
        (["--check", "--confirm"], "--confirm requires --apply."),
        (["--apply"], "Apply execution requires --confirm."),
    ],
)
def test_entrypoint_classifies_run_contract_failures_as_validation_errors(
    output_format: str, run_arguments: list[str], message: str
) -> None:
    stdout, stderr = StringIO(), StringIO()

    result = cli(
        [
            "--output",
            output_format,
            "run",
            "--playbook",
            "site.yml",
            "--revision",
            "main",
            *run_arguments,
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert result == ExitCode.VALIDATION_ERROR
    if output_format == "text":
        assert stdout.getvalue() == ""
        assert message in stderr.getvalue()
        assert "Error code: VALIDATION_ERROR" in stderr.getvalue()
    else:
        assert stderr.getvalue() == ""
        payload = (
            json.loads(stdout.getvalue())
            if output_format == "json"
            else yaml.safe_load(stdout.getvalue())
        )
        assert payload["status"] == "error"
        assert payload["error"]["code"] == "VALIDATION_ERROR"
        assert payload["error"]["category"] == "validation"
        assert payload["error"]["message"] == message


def test_entrypoint_preserves_concrete_typed_error_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout, stderr = StringIO(), StringIO()

    def fail(*args: object, **kwargs: object) -> int:
        assert kwargs["propagate_errors"] is True
        raise WorkspaceNotFoundError("Workspace was not found.")

    monkeypatch.setattr("ansiblectl.cli.main.main", fail)

    result = cli(["--output", "json", "workspace", "show"], stdout=stdout, stderr=stderr)

    payload = json.loads(stdout.getvalue())
    assert result == ExitCode.VALIDATION_ERROR
    assert stderr.getvalue() == ""
    assert payload["command"] == "workspace show"
    assert payload["error"]["code"] == "WORKSPACE_NOT_FOUND"
    assert payload["error"]["category"] == "not_found"


def test_entrypoint_debug_mode_reports_safe_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout, stderr = StringIO(), StringIO()

    def fail(*args: object, **kwargs: object) -> int:
        raise RuntimeError("token=do-not-expose")

    monkeypatch.setattr("ansiblectl.cli.main.main", fail)

    result = cli(["--debug", "status"], stdout=stdout, stderr=stderr)

    assert result == EXIT_UNEXPECTED_FAILURE
    assert "Cause type: RuntimeError" in stderr.getvalue()
    assert "do-not-expose" not in stderr.getvalue()


def test_entrypoint_renders_invalid_json_arguments_as_one_safe_document() -> None:
    stdout, stderr = StringIO(), StringIO()

    result = cli(
        ["--output-format", "json", "--password=do-not-echo"],
        stdout=stdout,
        stderr=stderr,
    )

    assert result == EXIT_INVALID_INPUT
    assert stderr.getvalue() == ""
    assert "do-not-echo" not in stdout.getvalue()
    payload = json.loads(stdout.getvalue())
    assert payload["schema_version"] == "1"
    assert payload["status"] == "error"
    assert payload["error"] == {
        "category": "usage",
        "code": "USAGE_ERROR",
        "context": {},
        "detail": None,
        "hint": "Run ansiblectl --help.",
        "message": "Invalid command arguments.",
    }
    assert len(payload["operation_id"]) == 26


def test_entrypoint_preserves_human_argparse_diagnostic() -> None:
    stdout, stderr = StringIO(), StringIO()

    with pytest.raises(SystemExit) as raised:
        cli(["status", "--unknown"], stdout=stdout, stderr=stderr)

    assert raised.value.code == EXIT_INVALID_INPUT
    assert stdout.getvalue() == ""
    assert "unrecognized arguments: --unknown" in stderr.getvalue()


def test_entrypoint_returns_human_help_successfully() -> None:
    stdout, stderr = StringIO(), StringIO()

    result = cli(["--help"], stdout=stdout, stderr=stderr)

    assert result == 0
    assert stderr.getvalue() == ""
    assert stdout.getvalue().startswith("usage: ansiblectl")
    assert "--output {text,json,yaml}" in stdout.getvalue()
    assert "Deprecated compatibility alias" in stdout.getvalue()


@pytest.mark.parametrize("output_format", ["json", "yaml"])
def test_entrypoint_wraps_help_in_machine_envelope(output_format: str) -> None:
    stdout, stderr = StringIO(), StringIO()

    result = cli(["--output", output_format, "--help"], stdout=stdout, stderr=stderr)

    payload = (
        json.loads(stdout.getvalue())
        if output_format == "json"
        else yaml.safe_load(stdout.getvalue())
    )
    assert result == 0
    assert stderr.getvalue() == ""
    assert payload["status"] == "success"
    assert payload["command"] == "ansiblectl"
    assert payload["data"]["help"].startswith("usage: ansiblectl")


def test_entrypoint_contains_unexpected_system_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout, stderr = StringIO(), StringIO()

    def terminate(*args: object, **kwargs: object) -> int:
        raise SystemExit("token=do-not-expose")

    monkeypatch.setattr("ansiblectl.cli.main.main", terminate)

    result = cli(["--output", "json", "status"], stdout=stdout, stderr=stderr)

    payload = json.loads(stdout.getvalue())
    assert result == EXIT_UNEXPECTED_FAILURE
    assert stderr.getvalue() == ""
    assert "do-not-expose" not in stdout.getvalue()
    assert payload["error"]["code"] == "INTERNAL_ERROR"

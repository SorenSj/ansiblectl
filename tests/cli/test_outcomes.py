"""CLI outcome rendering contract tests."""

import json
from io import StringIO

from ansiblectl.cli.outcomes import render_outcome
from ansiblectl.domain.outcomes import CommandOutcome, OutcomeKind


def test_json_failure_is_decoration_free_redacted_and_has_documented_exit_code() -> None:
    stdout, stderr = StringIO(), StringIO()
    outcome = CommandOutcome(
        OutcomeKind.VALIDATION_FAILURE,
        "config show",
        {"token": "hidden"},
        "invalid field",
        "Fix config.yaml.",
    )

    result = render_outcome(outcome, "json", stdout, stderr)

    assert result == 2
    assert stderr.getvalue() == ""
    assert json.loads(stdout.getvalue()) == {
        "data": {"token": "<redacted>"},
        "kind": "validation_failure",
        "operation": "config show",
        "reason": "invalid field",
        "remediation": "Fix config.yaml.",
    }


def test_human_operational_failure_is_actionable() -> None:
    stdout, stderr = StringIO(), StringIO()
    outcome = CommandOutcome(
        OutcomeKind.OPERATIONAL_FAILURE,
        "workspace show",
        reason="not found",
        remediation="Run workspace init.",
    )

    assert render_outcome(outcome, "human", stdout, stderr) == 1
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == "workspace show failed: not found Next: Run workspace init.\n"


def test_cancellation_and_unexpected_exit_codes_are_stable() -> None:
    stream = StringIO()
    assert (
        render_outcome(CommandOutcome(OutcomeKind.CANCELLED, "run"), "json", stream, StringIO())
        == 3
    )
    assert (
        render_outcome(
            CommandOutcome(OutcomeKind.UNEXPECTED_FAILURE, "run"), "json", stream, StringIO()
        )
        == 70
    )


def test_human_success_and_nested_sensitive_values_render_safely() -> None:
    stdout, stderr = StringIO(), StringIO()
    outcome = CommandOutcome(OutcomeKind.SUCCESS, "status", {"items": [{"password": "hidden"}]})

    assert render_outcome(outcome, "human", stdout, stderr) == 0
    assert stdout.getvalue() == "status: completed\n"
    machine_output = StringIO()
    render_outcome(outcome, "json", machine_output, stderr)
    assert json.loads(machine_output.getvalue())["data"]["items"][0]["password"] == "<redacted>"

"""Render typed command outcomes and map them to stable process exit codes."""

import json
from typing import TextIO

from ansiblectl.domain.outcomes import CommandOutcome, OutcomeKind
from ansiblectl.domain.redaction import redact

EXIT_CODES = {
    OutcomeKind.SUCCESS: 0,
    OutcomeKind.OPERATIONAL_FAILURE: 1,
    OutcomeKind.VALIDATION_FAILURE: 2,
    OutcomeKind.CANCELLED: 3,
    OutcomeKind.UNEXPECTED_FAILURE: 70,
}


def render_outcome(
    outcome: CommandOutcome, output_format: str, stdout: TextIO, stderr: TextIO
) -> int:
    payload = _payload(outcome)
    if output_format == "json":
        print(json.dumps(payload, sort_keys=True), file=stdout)
    elif outcome.is_success:
        print(f"{outcome.operation}: completed", file=stdout)
    else:
        print(_human_failure(outcome), file=stderr)
    return EXIT_CODES[outcome.kind]


def _payload(outcome: CommandOutcome) -> dict[str, object]:
    payload: dict[str, object] = {"kind": outcome.kind, "operation": outcome.operation}
    if outcome.data is not None:
        payload["data"] = redact(outcome.data)
    if outcome.reason is not None:
        payload["reason"] = outcome.reason
    if outcome.remediation is not None:
        payload["remediation"] = outcome.remediation
    return payload


def _human_failure(outcome: CommandOutcome) -> str:
    text = f"{outcome.operation} failed: {outcome.reason or 'unknown failure.'}"
    return f"{text} Next: {outcome.remediation}" if outcome.remediation else text

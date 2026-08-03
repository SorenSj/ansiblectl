"""Render typed command outcomes and map them to stable process exit codes."""

import json
from typing import TextIO

from ansiblectl.domain.outcomes import CommandOutcome, OutcomeKind

EXIT_CODES = {
    OutcomeKind.SUCCESS: 0,
    OutcomeKind.OPERATIONAL_FAILURE: 1,
    OutcomeKind.VALIDATION_FAILURE: 2,
    OutcomeKind.CANCELLED: 3,
    OutcomeKind.UNEXPECTED_FAILURE: 70,
}
_SENSITIVE_FIELDS = {"secret", "token", "password", "credential", "key"}


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
        payload["data"] = _redact(outcome.data)
    if outcome.reason is not None:
        payload["reason"] = outcome.reason
    if outcome.remediation is not None:
        payload["remediation"] = outcome.remediation
    return payload


def _redact(value: object) -> object:
    if isinstance(value, dict):
        return {
            name: "<redacted>" if name.lower() in _SENSITIVE_FIELDS else _redact(item)
            for name, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _human_failure(outcome: CommandOutcome) -> str:
    text = f"{outcome.operation} failed: {outcome.reason or 'unknown failure.'}"
    return f"{text} Next: {outcome.remediation}" if outcome.remediation else text

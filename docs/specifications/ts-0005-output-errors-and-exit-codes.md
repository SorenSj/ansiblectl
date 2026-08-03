# TS-0005: Output, Errors, and Exit Codes

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-03 |
| Related ADRs | [ADR index](../adr/README.md) |

## Purpose

Defines the boundary between structured application outcomes and human or machine-facing CLI responses.

## Scope

This specification defines the initial public and internal contract for this capability. Implementation details that do not alter the stated contract remain flexible.

## Functional requirements

1. Application services MUST return typed success or failure outcomes.
2. The CLI MUST map outcomes to human text, machine-readable schemas, and documented exit codes.
3. Machine-readable output MUST contain no decoration outside the selected format.
4. Errors MUST state the operation, reason, and safe next action when known.
5. Diagnostics, logs, and output MUST redact secrets and sensitive values.

## Interfaces and data

A command result contains a result kind, data model, diagnostics, and optional remediation. The renderer owns all terminal formatting.

The initial JSON schema has `kind`, `operation`, and optional `data`, `reason`,
and `remediation` fields. Exit codes are: success `0`, expected operational
failure `1`, validation failure `2`, cancellation `3`, and unexpected failure
`70`. Fields named `secret`, `token`, `password`, `credential`, or `key` are
rendered as `<redacted>`.

The `run` command maps a classified `cancelled` execution to exit code `3` in
both human and machine-readable output modes. Failed and timed-out executions
remain expected operational failures with exit code `1`.

The installed console entry point maps otherwise unhandled `Exception`
failures to a generic redacted outcome and exit code `70`. JSON mode remains a
single structured document. `KeyboardInterrupt` is not intercepted by this
boundary.

When JSON output is selected, argparse validation failures are replaced with
one redacted `validation_failure` document on stdout and exit code `2`; raw
argument diagnostics are discarded so argument values cannot leak. Human mode
retains argparse's usage and diagnostic text on stderr.

## Verification

- The same application failure renders consistently in human and machine modes.
- A machine-readable error validates against its documented schema.
- Exit-code tests cover validation, expected operational, cancellation, and unexpected failures.

## Non-goals

This specification does not introduce unrelated delivery mechanisms, hosted services, or public APIs beyond the contract described above.

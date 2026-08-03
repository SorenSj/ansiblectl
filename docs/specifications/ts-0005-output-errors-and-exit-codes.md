# TS-0005: Output, Errors, and Exit Codes

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 2.0 |
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

A command returns a typed `CommandResult` or raises an `AnsiblectlError`. The
renderer owns all terminal formatting. JSON and YAML use the versioned
[command envelope v1 schema](../schemas/command-envelope-v1.schema.json).

Every envelope contains `schema_version`, `status`, `operation_id`, `command`,
`changed`, `warnings`, and `metadata`. Success additionally contains `message`
and `data`; failure contains a structured `error`. Machine output is one
document on stdout with no decoration. Human failures are written to stderr.
Operation IDs are canonical ULIDs and increase monotonically within one
process, including concurrent calls and backwards wall-clock adjustments.
After a process fork, the child resets inherited generator state and obtains
fresh secure randomness before issuing another operation ID.
Command identity contains lowercase command and subcommand tokens only; it
never contains option or positional values. Context flags are runtime-validated
as booleans, and rejected output-format values are not retained in errors.
Command results and warnings validate their runtime field types. Warning codes
use the schema's uppercase identifier format, and context and metadata mappings
are defensively copied into immutable views.
Public errors require non-empty message fields, string-keyed context mappings,
and real exception causes. Their context is defensively copied and immutable,
and each error class is checked against the stable registry on construction.
Direct envelope construction enforces the same schema constants and field
types as factory construction. Structured error context and envelope metadata
are defensively copied into immutable views.
Human rendering converts C0, DEL, and C1 terminal control characters in public
values to visible hexadecimal escapes. Machine payload values remain unchanged
and are escaped by their JSON or YAML serializer.
Legacy cancellation status `3` is translated atomically to the Phase 1
`OPERATION_CANCELLED` envelope and process exit code `130` in every output
format. Any partial legacy result or diagnostic is discarded.
Command syntax rejected by argparse is `USAGE_ERROR` (`2`). Parsed command
arguments that violate an application contract are `VALIDATION_ERROR` (`4`),
including incompatible `run` mode and confirmation selections.
Inventory, syntax-check, and Ansible process results that fail or time out map
to `EXTERNAL_TOOL_ERROR` (`5`). Policy-denied preflight or execution maps to
`PERMISSION_DENIED` (`6`). Their partial legacy result is discarded.
The success `changed` flag is true only when a structured result explicitly
reports a mutation. During legacy adaptation this includes applied invalidation
of an existing state entry and applied pruning that removes execution records;
ambiguous operations remain conservatively false.
Explicit non-fatal inventory `diagnostics` and playbook `findings` are lifted
into success-envelope warnings with stable codes. Other fields and rendered
text are not interpreted as warnings.

The stable exit codes are success `0`, general error `1`, CLI usage error `2`,
configuration error `3`, validation error `4`, external-tool error `5`,
resource conflict `6`, authentication or secrets error `7`, plugin error `8`,
migration error `9`, and interruption `130`.

The installed entry point maps otherwise unhandled exceptions to
`INTERNAL_ERROR` without exposing their messages. `KeyboardInterrupt` maps to
`OPERATION_CANCELLED`. Argparse failures in machine modes map to `USAGE_ERROR`;
raw argument diagnostics are discarded. Human argparse diagnostics remain on
stderr. Failures while adapting an internal command result to the public
machine envelope are contained by the same exception boundary; partial
internal output is discarded. Unstructured diagnostics captured from legacy
commands are emitted only in text mode and are discarded in machine modes.
Successful parser exits render help normally in text mode and wrap it in a
success envelope in machine modes. Other `SystemExit` values are contained as
`INTERNAL_ERROR`; their values are never exposed.

The global Phase 1 interface is `--output text|json|yaml`, with
`ANSIBLECTL_OUTPUT` as its environment default. The deprecated
`--output-format human|json` spelling remains available during migration.
When both command-line spellings are present, `--output` takes precedence
regardless of argument order.
Generated CLI help lists `--output` as the primary interface and labels
`--output-format` as deprecated compatibility.
Invalid command-line or environment output selections fail with `USAGE_ERROR`;
the rejected value is not retained in public error context.

Fields whose names identify secrets, tokens, passwords, credentials, or keys
are recursively rendered as `<redacted>`, including compound names such as
`github_token` and `private-key`.

Before public rendering, paths and enum values are converted to their
public scalar values, sets are ordered deterministically, and non-finite floats
become `null`. Unsupported objects are represented only by a value-free type
marker; their `repr` or `str` methods are never invoked.
Recursive redaction is bounded to 64 container levels. Circular references and
deeper structures are replaced with stable value-free markers before
serialization.

## Verification

- The same application failure renders consistently in human and machine modes.
- A machine-readable error validates against its documented schema.
- Exit-code tests cover validation, expected operational, cancellation, and unexpected failures.

## Non-goals

This specification does not introduce unrelated delivery mechanisms, hosted services, or public APIs beyond the contract described above.

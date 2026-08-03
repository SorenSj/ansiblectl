# TS-0015: Event Publication and Subscription

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-03 |
| Related ADRs | [ADR index](../adr/README.md) |

## Purpose

Defines typed event registration, publication, subscription, and failure handling for optional observers.

## Scope

This specification defines the initial public and internal contract for this capability. Implementation details that do not alter the stated contract remain flexible.

## Functional requirements

1. Only documented event names and payload schemas are public.
2. Events MUST be published after the corresponding use-case transition is complete.
3. Subscriber failure MUST be isolated and MUST NOT invalidate core correctness unless explicitly specified.
4. Event payloads MUST contain no secret material.
5. Public event schema changes MUST follow SDK compatibility rules.

## Interfaces and data

The event service publishes a typed event to registered SDK subscribers and records safe delivery diagnostics.

The initial public event names are `execution.completed` and
`workspace.initialized`. Payloads are redacted before subscribers receive them;
subscriber exceptions are recorded by event name and exception class without
changing the completed use-case result.

The `execution.completed` payload contains the execution identifier, status,
exit code, elapsed time, optional stdout and stderr references, and an optional
safe diagnostic. It contains no raw process output.

When present, `execution.completed` also carries a structured `targeting`
object containing the host limit, selected tags, and skipped tags.
The payload also identifies execution mode as `check` or `apply`.

## Verification

- A subscriber receives the documented payload type.
- A failing optional subscriber does not change the use-case result.
- Secret redaction tests cover event payload creation.

## Non-goals

This specification does not introduce unrelated delivery mechanisms, hosted services, or public APIs beyond the contract described above.

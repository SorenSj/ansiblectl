# TS-0024: Local Event Delivery Operations

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-04 |
| Related ADRs | [ADR-0041](../adr/0041-local-event-delivery-runner.md), [ADR-0040](../adr/0040-durable-event-outbox.md), [ADR-0013](../adr/0013-cli-user-experience-and-exit-codes.md), [ADR-0020](../adr/0020-machine-readable-output-contract.md) |

## Purpose

Define a bounded local delivery-runner and safe operator CLI over the durable event outbox without
introducing a concrete remote transport or background service.

## Scope

This specification covers the application delivery port, one-attempt and bounded-batch
orchestration, stable adapter outcomes, local consumer operations, versioned output, and
compatibility with the v0.5 storage contract.

## Delivery adapter and runner

The delivery adapter port accepts one `DurableEventEnvelope` and returns exactly one typed outcome:

- `delivered`, with no diagnostic payload; or
- `failed`, with a canonical non-secret reason code.

The port MUST NOT receive a workspace path, SQLite connection, consumer cursor, claim token,
credential container, or raw domain event. An adapter exception maps to the stable
`ADAPTER_FAILURE` reason. Exception text, response bodies, headers, endpoint names, environment
values, and credentials MUST NOT be persisted or rendered.

One runner step performs these actions in order:

1. Claim the exact next due event for one canonical registered consumer.
2. Return `idle` without calling the adapter when no event is due.
3. Call the injected adapter outside any SQLite transaction.
4. Acknowledge the exact claim on `delivered`.
5. Record the exact claim failure using the configured deterministic retry profile on `failed` or
   adapter exception.

A bounded batch accepts a positive `max_events` and repeats runner steps until it reaches that
bound, becomes idle, or records a failure. It MUST stop after a failure so strict ordering and retry
scheduling remain visible. It MUST NOT sleep, poll indefinitely, spawn, daemonize, or add jitter.
Concurrent runners rely on the v0.5 lease token; a stale completion cannot advance or overwrite the
current claim.

## Safe result contracts

Runner result schema version 1 contains:

- consumer identifier;
- state: `delivered`, `failed`, or `idle`;
- delivered count;
- failed count;
- last event identifier and sequence, or null;
- stable failure reason, or null.

It contains no event payload, claim token, timestamps controlled by an adapter, paths, endpoint
data, or exception text. Batch results aggregate only these safe counters and the last attempted
event identity.

## Operator CLI

The local CLI command group is:

- `event consumer register NAME --start-sequence N`;
- `event consumer inspect`;
- `event consumer retry NAME --sequence N --event-id ID`;
- `event consumer abandon NAME --sequence N --event-id ID [--apply]`;
- `event retention [--apply]`.

Registration is idempotent only for the same starting sequence. Inspection is always read-only and
never displays payloads, failure details, claim tokens, database paths, or workspace paths. Retry
uses an exact consumer, sequence, and event identifier. Abandon and retention preview by default;
mutation requires `--apply`. Commands operate only on the explicitly resolved local workspace.

Human, JSON, and YAML output MUST represent the same safe typed result. Machine output uses
`schema_version: 1`, stable field names, deterministic ordering, and the existing command-envelope
and error contracts. Expected state conflicts use the existing `STATE_ERROR` contract.

## Configuration

Runner construction receives an explicit immutable retry profile containing a positive maximum
attempt count, positive integer delay seconds, and a positive lease duration. Defaults are defined
in the composition root and are identical across supported platforms. CLI operator commands do not
silently change this profile.

## Verification

- A fake adapter proves delivered, failed, exception, idle, and bounded-batch transitions.
- An adapter is never called while no event is due or after the first failed batch item.
- Concurrent and expired claims preserve v0.5 stale-worker fencing.
- Runner results and human, JSON, and YAML output contain no event payload or adapter detail.
- Register, retry, abandon, and retention enforce exact targeting and preview-first mutation.
- Existing v0.5 databases open without destructive migration and retain cursor state.
- Existing event subscribers, execution history, CLI commands, SDK imports, and exit codes remain
  compatible.
- The complete supported Python and operating-system CI matrix passes.

## Non-goals

- HTTP, RPC, webhook, broker, email, or hosted delivery implementations.
- Endpoint discovery, authentication, authorization, tenancy, TLS policy, or credential storage.
- A scheduler, daemon, service installer, background thread, or infinite polling loop.
- Exactly-once delivery, automatic abandon, automatic retention, or database access by adapters.

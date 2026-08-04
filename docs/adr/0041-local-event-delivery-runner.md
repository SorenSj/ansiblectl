# ADR-0041: Local Event Delivery Runner

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-04 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0040](0040-durable-event-outbox.md), [ADR-0030](0030-remote-api-deferral.md), [ADR-0032](0032-plugin-event-compatibility.md), [TS-0024](../specifications/ts-0024-local-event-delivery-operations.md) |

## Context

Version 0.5 established durable storage, independent consumer cursors, ordered claims, retry state,
operator recovery, and safe retention. Those mechanisms currently form an infrastructure boundary;
there is no application service that coordinates one delivery attempt and no CLI surface for an
operator to inspect or recover consumer state.

Adding a concrete webhook, message broker, or remote API now would combine delivery orchestration
with authentication, endpoint policy, credential storage, and network failure semantics. Those
concerns require separate decisions. The local orchestration and operator boundary can be made
useful and testable first without selecting a transport.

## Decision

Version 0.6 introduces a local delivery-runner application service over the v0.5 outbox contract.
The service receives an injected delivery adapter port. One bounded invocation claims the exact
next due event, calls the adapter outside the SQLite transaction, and then atomically acknowledges
success or records one stable failure reason. It never loops without an explicit positive bound,
sleeps, schedules itself, or owns a background process.

Adapters receive only the immutable redacted envelope. They return a typed success or stable
failure classification; raw exception messages, response bodies, credentials, and endpoint data
do not cross into persisted state or public output. Unexpected adapter exceptions map to one
documented stable reason while preserving the original exception only as an internal cause.

The CLI gains a local `event` command group for consumer registration, payload-free inspection,
exact retry, preview-first abandon, and preview-first retention. Destructive operations require
`--apply`. Human, JSON, and YAML render the same versioned safe result models. CLI commands do not
load plugins, discover endpoints, make network requests, or accept credentials.

## Consequences

- Delivery orchestration becomes independently testable with deterministic fake adapters.
- Future transports implement one narrow port without receiving database access.
- Operator recovery becomes available through the existing CLI safety and output contracts.
- Running delivery remains an explicit caller responsibility until a separately governed scheduler
  or daemon is approved.
- The v0.5 storage schema and public event envelopes remain compatible.

## Alternatives considered

Embedding delivery callbacks in the SQLite adapter was rejected because it would hold storage and
network concerns in one boundary. A background daemon was rejected because lifecycle, ownership,
shutdown, and service installation are not yet specified. A webhook implementation was rejected
because endpoint trust, credentials, TLS policy, and response classification require a dedicated
transport ADR. Exposing raw outbox SQL through the CLI was rejected because it would bypass typed
redaction and exact-match safety contracts.

## Compliance

TS-0024 defines runner state transitions, adapter results, operator commands, output schemas, and
verification. Concrete HTTP, RPC, broker, authentication, tenancy, secret storage, daemon, or
scheduler behavior requires another ADR before implementation.

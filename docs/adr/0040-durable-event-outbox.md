# ADR-0040: Durable Event Outbox

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-04 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0018](0018-event-publication-model.md), [ADR-0030](0030-remote-api-deferral.md), [ADR-0032](0032-plugin-event-compatibility.md), [TS-0023](../specifications/ts-0023-durable-event-delivery.md) |

## Context

The current event bus safely isolates in-process subscribers, and the workspace JSONL log provides
an audit history. Neither contract gives an external delivery adapter a durable cursor, retry
state, or a way to resume after process termination. Treating the audit log as a queue would couple
retention to delivery and would not provide transactional acknowledgements.

Ansiblectl needs a local, inspectable handoff boundary before any remote transport is introduced.
The boundary must preserve public event compatibility, redact before persistence, tolerate
multiple processes, and remain useful offline.

## Decision

Version 0.5 introduces a workspace-scoped durable event outbox backed by SQLite from the Python
standard library. The outbox is distinct from execution history. It stores a versioned safe event
envelope, a monotonically increasing workspace sequence, and per-consumer delivery state.

Appending an event and allocating its sequence occur in one database transaction. A committed
record is immutable. Each configured consumer advances its own checkpoint only by acknowledging
the next sequence, producing ordered at-least-once delivery. Delivery adapters receive already
redacted envelopes and never raw domain objects.

Failures are recorded with bounded attempt counts, a deterministic retry schedule, and stable
redacted reason codes. A failed earlier record blocks later records for that consumer. Exhausted
records remain blocked until an explicit operator retry or abandon action; abandon is audited and
does not delete the event. Automatic skipping, unbounded tight retries, and exactly-once claims are
forbidden.

The database and its lock/journal files are private workspace state. Implementations reject
symbolic links, apply restrictive creation permissions, use bounded transactions, and perform
schema validation before mutation. Retention may remove an event only after every configured
consumer has acknowledged or explicitly abandoned it.

## Consequences

- Process restarts and temporary adapter failures no longer lose committed outbox records.
- Consumers must be idempotent because acknowledgement can be lost after successful delivery.
- Strict per-consumer ordering can intentionally create backpressure behind a failed event.
- SQLite adds no third-party runtime dependency but requires filesystem capability and corruption
  tests on every supported platform.
- A future remote adapter can consume the port without moving transport concerns into the domain.

## Alternatives considered

Reusing the JSONL audit history was rejected because retention and append-only diagnostics do not
provide independent consumer checkpoints. One file per event was rejected because ordering and
multi-process cleanup become fragile. An embedded broker was rejected as operationally excessive.
Exactly-once delivery was rejected because ansiblectl cannot atomically commit a remote consumer's
side effects.

## Compliance

TS-0023 defines envelope fields, transaction boundaries, retry state, ordering, recovery, and
verification. Introducing HTTP, RPC, hosted coordination, authentication, tenancy, or automatic
dead-letter deletion requires a separate ADR.

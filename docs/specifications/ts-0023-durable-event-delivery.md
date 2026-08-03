# TS-0023: Durable Event Delivery

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-04 |
| Related ADRs | [ADR-0040](../adr/0040-durable-event-outbox.md), [ADR-0018](../adr/0018-event-publication-model.md), [ADR-0032](../adr/0032-plugin-event-compatibility.md) |

## Purpose

Define deterministic local persistence, ordering, acknowledgement, retry, and retention for public
events before any remote delivery protocol exists.

## Scope

This specification covers a workspace SQLite outbox, typed producer and consumer ports, safe event
envelopes, and operator-controlled recovery. It extends the existing best-effort in-process event
bus without changing its subscriber contract or using execution history as a queue.

## Durable envelope

Schema version 1 contains:

- `schema_version`: integer `1`;
- `event_id`: canonical monotonic ULID;
- `sequence`: positive integer allocated monotonically within one workspace;
- `name`: a documented public event name;
- `occurred_at`: UTC timestamp with microsecond precision and a `Z` suffix;
- `operation_id`: canonical operation ULID or `null` when the producer has none;
- `payload`: recursively redacted JSON object with string keys.

Payloads use the documented event schema from TS-0015. They MUST NOT contain credentials, secret
values, raw process output, absolute workspace paths, unsupported object representations, NaN, or
infinity. One encoded envelope is limited to 256 KiB. Validation and redaction occur before the
transaction that persists it.

## Storage and transactions

The store uses `.ansiblectl/events/outbox.sqlite3` with schema version 1, foreign keys enabled,
bounded busy handling, and durable transaction settings. The database and SQLite auxiliary files
MUST be regular non-symlink files inside the selected workspace and owner-only at creation.

One append transaction allocates the next sequence and inserts the immutable envelope. Concurrent
writers MUST produce unique contiguous committed sequences. Rollback does not consume a sequence.
Opening an unknown schema, corrupt database, unsafe path, or unsupported filesystem fails closed
with a stable public reason and does not recreate or truncate evidence automatically.

Consumer identifiers are canonical non-secret names. Registration establishes the first desired
sequence without rewriting event data. Claiming returns only the consumer's lowest pending
sequence. Acknowledgement and failure updates compare the expected event identifier and sequence
inside one transaction so stale workers cannot advance a checkpoint.

## Delivery semantics

Delivery is ordered and at-least-once per consumer:

1. Read the lowest due, unacknowledged sequence for one consumer.
2. Deliver the already-redacted envelope through an injected adapter.
3. On success, atomically acknowledge that exact record.
4. On failure, atomically increment its attempt count and set the next eligible time.
5. Do not offer a later sequence while an earlier record is pending, delayed, or exhausted.

The retry schedule is deterministic from persisted attempt count and configured bounded delays; it
uses no random jitter. Attempts stop at the configured positive maximum. The stored failure state
contains only a stable reason code and timestamps, never exception text, response bodies,
credentials, or environment values.

Consumers MUST make side effects idempotent by `event_id`. Ansiblectl does not claim exactly-once
delivery because a process can terminate after adapter success and before local acknowledgement.

## Recovery and retention

Inspection is read-only and reports counts, lowest pending sequence, attempt count, next retry time,
and stable state without payloads or filesystem paths. Operator retry resets scheduling for one
exact blocked consumer/event pair. Operator abandon requires an explicit apply action, records an
audit event, advances only that consumer, and preserves the immutable event until retention.

Retention removes only a contiguous acknowledged-or-abandoned prefix shared by every configured
consumer. Preview is the default. Active claims, unknown consumers, and events still needed by any
consumer prevent removal.

## Verification

- Restart tests deliver committed records without duplicating acknowledged records.
- Termination before and after adapter success demonstrates documented at-least-once behaviour.
- Multiprocess writers allocate unique ordered sequences without malformed envelopes.
- Stale acknowledgements and out-of-order advancement fail safely.
- Retry timing is deterministic, bounded, and blocks later records for the same consumer.
- Corruption, schema mismatch, symlinks, oversized envelopes, and unsafe payloads preserve evidence.
- Inspection and failure output remain redacted in human, JSON, and YAML formats.
- Existing in-process subscribers and execution-history retention remain backward compatible.

## Non-goals

- HTTP, RPC, webhooks, hosted brokers, or a remote control plane.
- Authentication, authorization, tenancy, endpoint discovery, or credential storage.
- Exactly-once delivery or distributed transactions with consumer side effects.
- Automatic event abandonment, payload mutation, or using the audit log as the outbox.

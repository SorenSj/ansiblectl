# ADR-0050: Workspace Event Archive

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-04 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0040](0040-durable-event-outbox.md), [ADR-0041](0041-local-event-delivery-runner.md), [ADR-0036](0036-transactional-filesystem-operations.md), [TS-0033](../specifications/ts-0033-workspace-event-archive.md) |

## Context

The durable outbox and delivery runner already provide ordered, at-least-once delivery to narrow
adapters. HTTPS webhooks are useful for connected receivers, but operators also need a local,
machine-readable audit surface that does not introduce network trust, credentials, a daemon, or a
second retry owner.

A shared append-only JSONL file looks simple but has an ambiguous crash boundary: termination after
an append becomes durable but before outbox acknowledgement causes the retry to append a duplicate.
Repairing that ambiguity would require a second journal, record scanning, or hidden exactly-once
claims. Arbitrary output paths would also expand the workspace trust boundary.

## Decision

Version 0.15 adds a workspace event archive delivery adapter. One canonical archive identifier maps
to the fixed private root `.ansiblectl/events/archives/ARCHIVE_ID/`. Each delivered event is stored
as one immutable canonical JSON file whose name binds its zero-padded sequence and event identifier.
Configuration cannot select an absolute path, parent traversal, symlink, alternate root, format,
template, command, compression program, or remote destination.

The adapter receives an existing durable envelope and writes its exact canonical delivery bytes.
Creation uses a private staging file, durable replacement, and parent-directory sync. A retry that
finds an existing regular file succeeds only when its bytes exactly match the expected envelope;
any mismatch, unsafe type, link, ownership, permission, or filesystem capability fails closed. The
delivery runner remains the sole owner of claims, retries, backoff, acknowledgement, and exhaustion.

Archive files are immutable application output. Ansiblectl does not rotate, truncate, delete,
rewrite, upload, index, or silently repair them. Operators may copy or remove a whole inactive
archive under an explicit external retention policy, but mutation during delivery is unsupported.
Public outcomes expose only stable archive success or failure semantics and never reveal workspace
paths, event payloads, filesystem metadata, temporary names, or exception values.

## Consequences

- Operators gain an offline, inspectable event archive without a network or secret boundary.
- One-file-per-event storage makes replay idempotence verifiable at the exact crash boundary.
- Disk capacity and retention remain explicit operator responsibilities.
- Consumers that require streaming JSONL can derive it deterministically from ordered archive files.
- A large archive trades inode usage for simple custody, verification, and failure semantics.

## Alternatives considered

Shared JSONL append was rejected because append durability and outbox acknowledgement cannot be one
atomic operation. Rewriting a single JSON array was rejected because cost and corruption exposure
grow with archive size. SQLite reuse was rejected because the archive must be a distinct export
surface, not privileged access to outbox internals. Arbitrary paths, stdout piping, commands, cloud
storage, syslog, and automatic rotation were deferred because each adds a separate trust or
lifecycle contract.

## Compliance

TS-0033 defines identifiers, layout, canonical bytes, custody, atomicity, replay, failure,
compatibility, redaction, and verification. Remote delivery, retention automation, background
workers, inbound APIs, hosted control planes, and a TUI remain out of scope.

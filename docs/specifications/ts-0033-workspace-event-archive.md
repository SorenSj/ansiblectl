# TS-0033: Workspace Event Archive

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-04 |
| Related ADRs | [ADR-0050](../adr/0050-workspace-event-archive.md), [ADR-0040](../adr/0040-durable-event-outbox.md), [ADR-0041](../adr/0041-local-event-delivery-runner.md), [ADR-0036](../adr/0036-transactional-filesystem-operations.md) |

## Purpose

Define a local, fail-closed delivery surface that exports durable event envelopes to immutable,
workspace-private files while preserving the existing ordered at-least-once runner contract.

## Selection and layout contract

An archive identifier MUST match `[a-z][a-z0-9._-]{0,127}`. It is a logical identifier, never a
path. The adapter maps it only to `.ansiblectl/events/archives/ARCHIVE_ID/` below the already
validated workspace root. Empty, uppercase, Unicode, separator-containing, parent, absolute,
overlong, URL, null, and non-string values are invalid.

One bounded foreground invocation selects the adapter explicitly as
`event deliver CONSUMER --archive ARCHIVE_ID --max-events N`. `--archive` and the existing
`--endpoint` selection are mutually exclusive and exactly one is required. The command does not
register a consumer implicitly, enumerate archives, print the selected identifier, or start a
background worker.

For envelope sequence `N` and canonical 26-character event identifier `E`, the only final filename
is the 20-digit zero-padded decimal sequence, one ASCII hyphen, the event identifier, and `.json`.
Sequence values outside `1..99999999999999999999` are rejected. No configured filename, extension,
subdirectory, interpolation, or collision suffix is accepted.

The `.ansiblectl`, `events`, and `archives` ancestors retain their existing private workspace
custody. A newly created archive directory MUST be owner-controlled mode `0700`. Existing archive
ancestors and targets MUST be directories or regular files as appropriate, owned by the effective
user, not symlinks, and not traversed through a replaced descriptor. Unsupported ownership,
no-follow, descriptor-relative, locking, replacement, or directory-sync capabilities fail closed.

## Canonical content contract

The file content is the existing bounded canonical webhook-delivery envelope JSON, encoded as
UTF-8 with sorted keys, compact separators, and no trailing newline. The adapter MUST NOT add an
archive schema wrapper, timestamp, hostname, workspace path, consumer identifier, retry count,
claim token, signature, credential, or derived metadata. The maximum content size remains the
existing canonical delivery payload limit.

The final mode is `0600`. The adapter MUST NOT preserve an ambient umask-derived wider mode,
extended template content, filesystem metadata, or caller-provided bytes. Public representation of
the adapter, archive identifier, and delivery request is redacted.

## Atomicity and replay contract

One attempt validates the archive identifier, envelope, ancestors, and final target before
mutation. For an absent target, it creates one private unpredictable staging file in the archive
directory, writes the complete content, syncs the file, applies exact mode, atomically installs the
final name without overwriting a concurrently created target, and syncs the directory. The staging
file is removed after any recoverable pre-install failure. No partial final file is observable.

If the final target already exists, the adapter opens it without following links and succeeds only
when it is one owner-controlled, single-link, mode-`0600` regular file on the expected device whose
complete bytes exactly equal the canonical expected content. This is an idempotent replay, not a
second write. A mismatch or unsafe target fails and is never overwritten, renamed, truncated,
deleted, repaired, or acknowledged as delivered.

Concurrent attempts for the same envelope may race, but at most one canonical final file is
installed; every successful contender verifies identical final bytes. Different sequences never
share a final target. The outbox acknowledgement remains a separate operation, so delivery is
at-least-once and crash recovery relies only on exact replay verification.

## Failure, lifecycle, and redaction contract

Archive validation, capacity, permission, capability, staging, write, sync, install, race, and
verification failures produce only the stable adapter outcome `ARCHIVE_UNAVAILABLE`. The adapter
does not retry internally. The existing delivery runner owns retry and exhaustion behavior and
does not special-case archive failures.

Archive identifiers, absolute and relative paths, staging names, payloads, event identifiers,
filesystem metadata, capacity details, operating-system errors, and exception values MUST NOT
appear in command output, logs, history, events, retry records, SQLite, crash-safe state, or object
representations. The canonical archive file intentionally contains the event envelope; that file
is the selected data surface and is not a diagnostic leak.

Ansiblectl never rotates, compacts, uploads, indexes, truncates, rewrites, or deletes archive files.
It does not monitor capacity in the background. Operator retention acts only outside an active
delivery attempt and accepts that deleting an archived file permits a later outbox retry to recreate
it if the corresponding event has not yet been acknowledged.

## Compatibility and verification

- Identifier and filename tests cover every invalid representation and sequence bound.
- Fixed vectors prove exact filenames, canonical bytes, mode, and absence of a trailing newline.
- Real-filesystem tests cover symlinks, hard links, special files, permissions, ownership where
  supported, ancestor replacement, target races, partial writes, sync failures, and capacity errors.
- Subprocess termination tests cover staging, file sync, install, directory sync, and the boundary
  before outbox acknowledgement.
- Replay tests prove identical content succeeds without mutation and mismatched content fails closed.
- Multiprocess tests prove same-event races install or verify one identical immutable result.
- Raw durable-byte and public-surface tests prove paths, identifiers, metadata, payloads, and
  exception details remain absent outside the selected archive file.
- Existing webhook consumers and outbox schema retain exact behavior and bytes.
- Hosted CI passes on Ubuntu and macOS with Python 3.12, 3.13, and 3.14.

## Non-goals

- JSONL append, mutable aggregate files, compression, rotation, retention scheduling, or indexing.
- Arbitrary paths, stdout or shell piping, templates, commands, plugins, syslog, or cloud storage.
- Exactly-once delivery, cross-filesystem atomicity, network filesystems, or multi-host writers.
- Background services, inbound APIs, hosted control planes, remote commands, or a TUI.

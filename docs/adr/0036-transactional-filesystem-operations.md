# ADR-0036: Transactional Filesystem Operations

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0012](0012-logging-and-observability.md), [ADR-0019](0019-local-state-cache-and-persistence.md) |

## Context

Ansiblectl persists workspace metadata and generated artifacts locally. A process failure between
multiple writes could previously leave a partially updated workspace. Atomic replacement protects
one file, but does not provide rollback or recovery across a set of files.

## Decision

Provide a local infrastructure primitive whose transactions are restricted to one configured root.
Callers explicitly stage byte writes and file deletions, then commit or roll back.
The workspace state adapter uses this primitive for persisted cache updates. Execution-history
retention uses it for the canonical event-log replacement, then removes derived output only after
that commit. Other adapters can migrate when an operation needs rollback rather than only
single-file replacement.

Each transaction uses an owner-only directory below `.ansiblectl/transactions`. Staged files and
backups therefore normally share the target filesystem. A versioned JSON journal is atomically
replaced and synced before and after every externally visible step. Commits take a workspace-level
advisory lock, preserve overwritten files, apply each target with atomic replacement where possible,
sync parent directories, and remove recovery data only after the committed state is durable.
Each operation records and syncs its rollback intent before changing the target. Recovery can
therefore safely replay rollback whether interruption happens immediately before or after the
visible replacement.

Recovery scans durable journals. It removes completed journals and rolls every other transaction
back in reverse operation order. Recovery is retryable: each restored operation is journaled before
the next. Unreadable journals and failed rollback are retained and reported with stable,
machine-readable exceptions for manual inspection.

Operators use `ansiblectl state recover` to preview opaque transaction identifiers. Recovery remains
read-only unless `--apply` is supplied, matching the established state and retention safety model.
Preview includes incomplete journals requiring rollback and committed journals requiring cleanup;
committed target state is preserved during cleanup.
Each live transaction holds an owner lock inside its journal directory. Process termination releases
that lock automatically; preview and recovery skip locked journals so they cannot roll back work
that another live process is still staging or committing.

Transaction lifecycle events use the existing structured logging port. They include transaction and
correlation identifiers plus operation counts, but never paths or file contents.

Targets are normalized and must remain below the configured root. Transaction control data,
directories, symlinks, and repeated targets are rejected. The initial contract handles regular
files only; target containment and parent identity are revalidated at commit to reject symlink
swaps after staging. Directory-tree transactions and cross-device targets are outside its scope.

## Consequences

- Multi-file updates can be recovered after process interruption without exposing partially staged
  content as committed state.
- Atomicity is per target, with transaction-level rollback. Readers that do not participate in the
  lock can observe intermediate targets during a multi-file commit.
- The local filesystem must provide reliable `fsync`, atomic rename, advisory locking, and regular
  file semantics. Network filesystems may weaken those guarantees.
- Retained corrupt journals intentionally block automatic recovery instead of guessing or deleting
  evidence.

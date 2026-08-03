# TS-0021: Operational Reliability

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-03 |
| Related ADRs | [ADR-0037](../adr/0037-operational-reliability-and-platform-contract.md), [ADR-0036](../adr/0036-transactional-filesystem-operations.md) |

## Purpose

Define the v0.3.0 reliability contract for transactional filesystem capability detection,
subprocess crash verification, multiprocess ownership, safe diagnostics, and operator recovery.

## Scope

This specification applies to regular-file transactions below one selected workspace root. It
strengthens the v0.2.0 contract without adding directory-tree transactions, remote control, or a
second transaction implementation.

## Functional requirements

1. A transaction MUST persist rollback intent before each externally visible target mutation.
2. Recovery MUST restore incomplete operations in reverse order and MUST be safe to retry after
   interruption at every recovery journal update.
3. A live transaction MUST hold an operating-system owner lock for its complete lifetime.
4. Preview and recovery MUST skip journals whose owner lock is held by another live process.
5. Process termination MUST release ownership without requiring application cleanup.
6. Committed journals left after process termination MUST preserve target state and require cleanup
   only.
7. Corrupt or unsupported journals MUST be retained and MUST fail with a stable recovery error.
8. Required filesystem capabilities MUST be verified or rejected before user-target mutation.
9. Capability probes MUST be workspace-scoped, owner-only, bounded, and removed after inspection.
10. Recovery diagnostics MUST conform to the safe schema below and pass recursive redaction.
11. Transaction and recovery operations MUST retain structured audit correlation without logging
    target paths or content.
12. No implementation MAY claim an operating-system/filesystem combination absent from the CI
    support matrix.

## Filesystem capability contract

The adapter requires all of the following:

- creation of owner-only regular files and directories;
- exclusive and shared advisory locks with non-blocking contention detection;
- atomic replacement within the target filesystem;
- durable syncing of file data and containing directories;
- stable canonical path containment during staging, commit, and rollback;
- rejection of symbolic-link substitution and non-regular targets;
- explicit classification of cross-device replacement as unsupported.

A capability result contains a schema version, supported boolean, platform identifier, filesystem
scope identifier, and stable reason codes. Human remediation may accompany reason codes, but raw
operating-system exception text is not public output.

Capability success is advisory evidence for the inspected workspace mount, not a permanent system
guarantee. Commit and rollback continue to handle runtime failures defensively.

## Recovery diagnostic contract

One diagnostic contains only:

- `schema_version`;
- opaque `transaction_id`;
- state from the documented journal state set;
- bounded `age_seconds` or `null` when trustworthy age cannot be established;
- action: `none`, `cleanup`, `rollback`, or `manual_inspection`;
- stable reason codes;
- whether an active owner lock prevents recovery.

Diagnostics MUST NOT expose paths, contents, modes, user or process identifiers, exception values,
or journal payloads. Unknown journal states map to `manual_inspection` rather than being guessed.

## Required subprocess crash matrix

Tests terminate a child process without application-level rollback at these checkpoints:

1. staging directory created before the first journal;
2. staged content synced before staging journal replacement;
3. committing state synced before backup creation;
4. backup synced before write-ahead applied intent;
5. applied intent synced before target replacement or deletion;
6. target changed before parent-directory sync;
7. target synced before the next committing journal update;
8. committed journal synced before transaction-directory cleanup;
9. backup restored before rolling-back journal update;
10. rolled-back journal synced before cleanup.

For every checkpoint, a new process performs preview and recovery. Assertions cover target content,
journal retention or cleanup, owner-lock release, idempotent second recovery, stable public errors,
and absence of leaked staged content in logs or diagnostics.

## Multiprocess contention matrix

Tests independently schedule:

- two commits targeting different files;
- two transactions attempting the same target;
- preview while another process stages and commits;
- recovery while another process owns a transaction;
- two simultaneous recovery processes;
- state persistence and execution-history retention competing for the workspace transaction lock.

The final state MUST be valid, live work MUST NOT be rolled back, and no process may observe raw
journal content through a public interface.

## Journal retention and repeated failure

Recovery never deletes corrupt journals automatically. A successfully committed journal is removed
on explicit applied recovery. A failed rollback remains available for another retry. The initial
v0.3.0 contract reports age and required action but does not automatically expire evidence.

Operator documentation MUST distinguish active, rollback-required, cleanup-only, and corrupt
journals. Manual deletion remains an explicit operator action outside the recovery command.

## Verification

- All crash checkpoints run as real subprocess tests on each claimed operating system.
- Multiprocess tests use bounded deadlines and fail rather than hanging indefinitely.
- Capability probe success and each stable failure reason have contract tests.
- Diagnostics have human and machine-readable rendering tests plus redaction tests.
- Existing v0.2.0 recovery, public error, state, history, documentation, and architecture tests remain
  green.
- Wheel, source archive, build metadata, and tagged-release inspection pass from a clean commit.

## Non-goals

- Directory creation, recursive deletion, or directory-tree rollback.
- Durability guarantees for network or userspace filesystems without a dedicated contract.
- Windows transaction support in the POSIX adapter.
- Automatic deletion of corrupt or old recovery evidence.
- Remote API, hosted control plane, or terminal UI.

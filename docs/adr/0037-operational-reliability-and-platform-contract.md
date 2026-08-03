# ADR-0037: Operational Reliability and Platform Contract

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0036](0036-transactional-filesystem-operations.md), [TS-0021](../specifications/ts-0021-operational-reliability.md) |

## Context

Version 0.2.0 introduced durable filesystem transactions, write-ahead rollback intent, owner locks,
and explicit recovery. Unit tests exercise journal transitions and simulated failures, but they do
not prove behaviour after operating-system process termination or across independently scheduled
processes. Filesystem guarantees also differ across platforms and mount types.

The project needs an explicit reliability boundary before it broadens the transaction surface or
claims support beyond the environment in which the primitives are implemented and tested.

## Decision

Version 0.3.0 focuses on operational reliability. Transaction guarantees are verified with real
subprocess termination at every externally visible journal transition and with multiprocess lock
contention. Tests must observe only public filesystem state and durable journals after the child
process has exited; test-only calls into private recovery methods are insufficient evidence for the
milestone.

The supported transaction platform is POSIX with:

- advisory `flock` semantics compatible with `fcntl`;
- atomic same-filesystem replacement of regular files;
- durable file and directory `fsync` operations;
- owner-only file and directory permissions;
- reliable detection of symbolic links and cross-device replacement failures.

Python support continues to follow package metadata and CI. Operating-system support is claimed
only for combinations exercised in CI. The v0.3 matrix covers Ubuntu and macOS on Python 3.12,
3.13, and 3.14. Windows is unsupported for transactional persistence until a locking adapter,
durability contract, and dedicated CI matrix are accepted.

Before mutation, the infrastructure adapter must either establish the required capability contract
or fail safely with a stable, actionable error. A successful probe is scoped to the selected
workspace filesystem and must not imply guarantees for another mount. Capability checks must not
modify user targets or retain probe content after success.

Recovery diagnostics expose only an opaque transaction identifier, journal state, bounded age, and
required operator action. Target paths, staged or backup content, raw exception values, process
arguments, and owner identifiers remain private. Repeated recovery failures retain evidence and do
not trigger automatic destructive cleanup.

## Consequences

- Reliability claims become evidence-based and bounded by a published platform contract.
- CI becomes slower because crash and contention tests use real subprocesses.
- Unsupported filesystems fail before target mutation instead of receiving best-effort guarantees.
- Windows users retain non-transactional package functionality only where it does not import or
  require the POSIX locking adapter; full Windows support remains future work.
- Recovery diagnostics become more useful while preserving the established redaction boundary.

## Alternatives considered

Treating existing unit tests as sufficient was rejected because in-process exceptions do not model
descriptor release, buffered writes, or process death. Claiming generic filesystem support was
rejected because rename, locking, and sync guarantees vary. Automatically deleting old or corrupt
journals was rejected because age alone does not prove that evidence is safe to discard.

## Compliance

TS-0021 defines the required crash matrix, diagnostic schema, capability behaviour, and verification
criteria. A material relaxation of the platform or durability contract requires a superseding ADR.

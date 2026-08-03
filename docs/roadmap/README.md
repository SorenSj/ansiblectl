# Ansiblectl roadmap

This roadmap records intended release milestones without turning exploratory ideas into public
compatibility promises. Work remains under `[Unreleased]`, and the package version remains at the
latest published release until a milestone satisfies its exit criteria.

## Completed milestones

### v0.1.0 — Local-first foundation

- Workspace, configuration, inventory, repository, plugin, policy, and execution foundations.
- Structured logging, state management, execution history, packaging, and release provenance.

### v0.2.0 — Safe boundaries and transactional persistence

- Stable errors, exit codes, command envelopes, redaction, and unexpected-failure containment.
- Transactional regular-file writes and deletions with durable journals and reverse rollback.
- Explicit recovery preview/application, owner locks, write-ahead intent, and retryable recovery.

## Active milestone

### v0.3.0 — Operational Reliability

The next feature release validates the Phase 2 guarantees under real operating-system failure and
concurrency conditions. It must not introduce a remote control plane or TUI.

Planned scope:

1. Add subprocess-based crash tests that terminate writers before replacement, after replacement,
   during rollback, and after durable commit.
2. Add multiprocess contention tests for staging, commit, preview, and recovery owner locks.
3. Detect and report unsupported or weakened filesystem capabilities before mutation, including
   atomic replacement, advisory locking, directory syncing, and cross-device targets.
4. Provide safe recovery diagnostics with transaction state, age, and required action while never
   exposing target paths, staged content, backup content, or exception values.
5. Define journal retention and operator guidance for corrupt or repeatedly failing recovery.
6. Publish the supported platform contract. The current implementation is POSIX-oriented because
   it uses `fcntl`; Windows support requires a separate locking adapter and dedicated CI coverage.

Exit criteria:

- [ADR-0037](../adr/0037-operational-reliability-and-platform-contract.md) and
  [TS-0021](../specifications/ts-0021-operational-reliability.md) define the capability and platform
  contracts before implementation is considered complete.
- Real subprocess termination tests demonstrate recovery at every durable journal transition.
- Concurrent recovery cannot mutate transactions owned by live processes.
- All new diagnostics pass redaction and stable-envelope tests.
- CI passes on every declared supported Python and operating-system combination.
- Documentation includes operator recovery procedures and known filesystem limitations.
- The complete quality, build, provenance, and tagged-release gates pass from a clean commit.

Explicit non-goals:

- Directory-tree transactions.
- Network-filesystem durability guarantees.
- Remote API, hosted control plane, or terminal UI.
- Moving or recreating an existing release tag.

## Candidate later milestones

### v0.4.0 — Plugin trust and unattended policy

- Plugin provenance and signing policy.
- Registry trust and distribution rules.
- Enterprise or unattended permission enforcement.

This milestone requires dedicated ADRs before its scope becomes normative.

### Future — Durable events and remote delivery

- Persistent event ordering, retries, and delivery guarantees.
- Remote API authentication, authorization, tenancy, lifecycle, and compatibility.
- A TUI implemented only as a delivery adapter over established application services.

These capabilities remain deferred under the existing ADRs and have no assigned version until the
local operational contracts are proven.

# Ansiblectl roadmap

This roadmap records intended release milestones without turning exploratory ideas into public
compatibility promises. Release preparation may set the next package version only after its
implementation and hosted-CI gates pass; publication still requires the immutable tagged-release
gate.

## Completed milestones

### v0.1.0 — Local-first foundation

- Workspace, configuration, inventory, repository, plugin, policy, and execution foundations.
- Structured logging, state management, execution history, packaging, and release provenance.

### v0.2.0 — Safe boundaries and transactional persistence

- Stable errors, exit codes, command envelopes, redaction, and unexpected-failure containment.
- Transactional regular-file writes and deletions with durable journals and reverse rollback.
- Explicit recovery preview/application, owner locks, write-ahead intent, and retryable recovery.

## Most recently completed milestone

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

- [x] [ADR-0037](../adr/0037-operational-reliability-and-platform-contract.md) and
  [TS-0021](../specifications/ts-0021-operational-reliability.md) define the capability and platform
  contracts before implementation is considered complete.
- [x] Real subprocess termination tests demonstrate recovery at every durable journal transition.
- [x] Concurrent recovery cannot mutate transactions owned by live processes.
- [x] All new diagnostics pass redaction and stable human, JSON, and YAML rendering tests.
- [x] Hosted CI passes on Ubuntu and macOS with Python 3.12, 3.13, and 3.14 in
  [PR #2](https://github.com/SorenSj/ansiblectl/pull/2).
- [x] Documentation includes operator recovery procedures and known filesystem limitations.
- [x] Local quality, build, provenance, and artifact-inspection gates pass from a clean commit.
- [x] The v0.3.0 package version and dated changelog are prepared after the hosted CI matrix passed.
- [x] The immutable v0.3.0 tag and
  [tagged artifact workflow](https://github.com/SorenSj/ansiblectl/actions/runs/30861466333) pass
  from merge commit `ad3813d`.

Readiness evidence was last reviewed on 2026-08-04. Version 0.3.0 is released, and its retained
workflow artifact is named `ansiblectl-v0.3.0`; no existing release tag was moved or recreated.

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

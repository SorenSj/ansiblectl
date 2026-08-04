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

## Completed milestone

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

## Most recently completed milestone

### v0.4.0 — Plugin trust and unattended policy

- Signed plugin provenance bound to exact artifact bytes, manifest identity, publisher key, and
  normalized distribution origin.
- Explicit registry and signing-key trust without trust-on-first-use or network installation.
- Default-deny unattended permission policy with deny precedence and non-interactive evaluation.
- Safe human, JSON, and YAML trust decisions before archive extraction or plugin import.

Exit criteria:

- [x] ADR-0038, ADR-0039, and TS-0022 define provenance, origin, signature, and unattended policy
  contracts before implementation.
- [x] Canonical provenance parsing and fixed-vector Ed25519 verification are implemented.
- [x] Artifact digest, manifest agreement, trusted-key, and origin checks occur before code import.
- [x] Unattended deny-overrides policy is deterministic and never prompts or persists approval.
- [x] Every stable decision reason has redacted human, JSON, and YAML contract tests.
- [x] Existing manifest discovery and interactive permission preflight remain compatible.
- [x] The complete quality, build, provenance, and release gates pass.
- [x] Hosted CI passes on Ubuntu and macOS with Python 3.12, 3.13, and 3.14 in
  [PR #10](https://github.com/SorenSj/ansiblectl/pull/10).
- [x] The immutable v0.4.0 tag and
  [tagged artifact workflow](https://github.com/SorenSj/ansiblectl/actions/runs/30863568837) pass
  from merge commit `a523dee`.

Readiness evidence was last reviewed on 2026-08-04. Version 0.4.0 is released, and its retained
workflow artifact is named `ansiblectl-v0.4.0`; no existing release tag was moved or recreated.

Explicit non-goals:

- Registry download, dependency resolution, or installation.
- Online key discovery, trust on first use, automatic revocation, or transparency-log availability.
- Hosted policy management, remote API, or plugin execution sandboxing.

## Active milestone

### v0.5.0 — Durable event outbox

- Workspace-scoped durable event envelopes with monotonic sequence allocation.
- Ordered at-least-once delivery with independent consumer acknowledgements.
- Deterministic bounded retry, explicit recovery, and safe prefix retention.
- Redacted inspection without introducing any remote transport or credential boundary.

Exit criteria:

- [x] ADR-0040 and TS-0023 define durability, ordering, acknowledgement, retry, and retention
  before implementation.
- [x] A schema-versioned SQLite outbox safely appends immutable redacted envelopes.
- [x] Consumer claims, acknowledgements, and stale-worker rejection preserve strict ordering.
- [ ] Restart, crash-window, multiprocess, corruption, and symlink tests pass.
- [ ] Retry, abandon, inspection, and retention are deterministic and redaction-safe.
- [ ] Existing in-process subscribers and execution-history retention remain compatible.
- [ ] The complete quality, build, provenance, and release gates pass.

Explicit non-goals:

- Remote delivery protocols, hosted brokers, endpoint credentials, authentication, or tenancy.
- Exactly-once guarantees or distributed transactions with consumer side effects.
- Automatic abandonment, unbounded retries, or using execution history as the outbox.

### Future — Remote delivery adapters

- Remote API authentication, authorization, tenancy, lifecycle, and compatibility.
- A TUI implemented only as a delivery adapter over established application services.

These capabilities remain deferred under the existing ADRs and have no assigned version until the
local operational contracts are proven.

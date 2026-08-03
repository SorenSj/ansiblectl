# Changelog

All notable changes to Ansiblectl are documented here.

## [Unreleased]

### Added

- ADR-0040 and TS-0023 defining the v0.5 durable event outbox, ordered at-least-once delivery,
  deterministic retry, operator recovery, and safe retention contracts.

## [0.4.0] - 2026-08-04

### Added

- Strict, bounded plugin provenance parsing with canonical domain-separated JSON payloads.
- Ed25519 signing-key identification, signature verification, streaming artifact hashing, and
  manifest agreement before plugin import.
- Exact provider-and-signing-key origin allowlists, including explicit local-origin trust.
- Pure unattended plugin-policy evaluation with deny precedence and local restriction ceilings.
- Redaction-safe human, JSON, and YAML trust-decision contracts for every stable reason.
- Compatibility coverage preserving manifest discovery and explicit interactive permission grants.

## [0.3.0] - 2026-08-04

### Added

- Roadmap and normative v0.3.0 operational-reliability contracts covering subprocess crash tests,
  multiprocess ownership, filesystem capability checks, safe recovery diagnostics, and supported
  platforms.
- Typed workspace filesystem capability reports, stable unsupported-capability errors, and a
  pre-transaction POSIX probe for permissions, advisory locks, atomic replacement, and syncing.
- Pre-staging rejection of nested cross-device targets with the stable `CROSS_DEVICE_TARGET` reason.
- Additive `state recover --details` diagnostics with bounded age, opaque identifiers, owner status,
  required action, and stable reason codes without journal paths or content.
- Stable human, JSON, and YAML rendering for detailed recovery diagnostics.
- Real subprocess termination coverage across staging, write-ahead commit, target replacement,
  automatic rollback, durable commit, and cleanup transitions.
- Bounded multiprocess contention coverage for different and shared targets, live-owner preview and
  recovery exclusion, and serialized simultaneous recovery.
- Multiprocess contention coverage for state persistence and execution-history retention sharing
  the workspace transaction lock.
- An operator recovery runbook covering safe inspection, automatic recovery, retained corrupt
  evidence, repeated failures, and supported filesystem limitations.
- An explicit Ubuntu and macOS CI support matrix for Python 3.12 through 3.14.
- Release artifact inspection for exact wheel/sdist names, safe source paths, typed package files,
  CLI entry points, dependency lock, documentation, and provenance metadata.

## [0.2.0] - 2026-08-03

### Added

- Durable transactional filesystem writes and deletions with rollback, interrupted-operation
  recovery, stable error contracts, and structured audit events.
- Workspace cache persistence now uses the transactional filesystem primitive.
- Execution-history retention transactionally replaces its canonical event log before deleting
  derived run output.
- `state recover` previews interrupted transaction identifiers and requires `--apply` before
  performing rollback or completed-journal cleanup.
- ADR 0036 documenting guarantees, failure semantics, and known filesystem limitations.
- Unified public error hierarchy, stable error-code registry, and documented process exit codes.
- Versioned command success and error envelopes with text, JSON, and YAML rendering.
- Public command context, structured result, warning, and envelope integration contracts.
- Canonical monotonic operation IDs with concurrent, clock-rollback, and process-fork safety.
- Published JSON Schema for command envelope version 1.

### Changed

- The primary output interface is now `--output text|json|yaml`, with `ANSIBLECTL_OUTPUT` support; `--output-format` remains as a deprecated compatibility alias.
- Installed CLI failures now pass through one typed exception boundary with consistent classification across output formats.
- Parsed application-contract violations, external-tool failures, policy denials, and cancellations now use their dedicated Phase 1 exit codes.
- Legacy command results are adapted atomically, including explicit change state and structured non-fatal warnings.
- Public context, result, warning, error, and envelope models now enforce runtime field validation and defensive immutability.

### Security

- Unexpected exception values, partial legacy output, and unstructured machine diagnostics are discarded at the CLI boundary.
- Public output recursively redacts sensitive named fields and safely bounds circular or excessively deep structures.
- Human output escapes terminal control characters, and unsupported objects are rendered without invoking value-bearing string representations.
- Command identity and invalid output selections no longer retain option or positional values.

## [0.1.0] - 2026-08-03

### Added

- Local-first workspace, configuration, inventory, repository, plugin, playbook, and execution CLI workflows.
- Policy-governed Ansible check/apply execution with safe preflight and private captured output.
- Versioned execution history inspection, filtering, retention, and summary contracts.
- Typed plugin SDK contracts, permission preflight, structured logging, and release provenance.

# Changelog

All notable changes to Ansiblectl are documented here.

## [Unreleased]

## [0.9.0] - 2026-08-04

### Added

- ADR-0044 and TS-0027 defining named, CIDR-bounded private webhook network policies without a
  general private-network bypass.
- A strict immutable policy model for canonical RFC 1918 and IPv6 unique-local ranges with bounded
  policy and network counts.
- Safe workspace policy loading with no-follow file access, regular-file and size checks, strict
  UTF-8, unique YAML keys, and rejection of aliases, anchors, and explicit tags.
- Webhook endpoint schema version 2 with one exact immutable network-policy binding; schema version
  1 remains supported and global-only.

### Changed

- Webhook destination validation now supports explicitly approved private addresses while requiring
  every DNS answer to satisfy the same selected policy.
- Operator documentation includes separate private-policy and endpoint-binding examples.

### Security

- Mixed, loopback, link-local, metadata, carrier-grade NAT, reserved, mapped, malformed,
  noncanonical, and out-of-policy address answers fail closed before connection.
- Policy identifiers, CIDRs, resolved addresses, hostnames, URLs, and resolver details remain absent
  from public and durable delivery surfaces.
- Connections remain bound to the validated immutable address tuple while TLS verifies the original
  DNS hostname through the platform trust store.

## [0.8.0] - 2026-08-04

### Added

- ADR-0043 and TS-0026 defining the production environment-secret provider's canonical key,
  exact lookup, lifecycle, composition, failure, and redaction contracts.
- A production `env:NAME` secret provider with exact single-key lookup and no environment
  enumeration, fallback, expansion, mutation, caching, or persistence.
- Bounded authenticated webhook CLI composition using process-supervisor or CI-injected secret
  material without adding secret values or keys to public or durable surfaces.

### Changed

- Authenticated webhook delivery now rejects unavailable or malformed material before DNS
  resolution or transport activity.
- The webhook operator documentation now includes the canonical environment-secret workflow and
  its fail-closed behavior.

### Security

- Environment keys accept only bounded uppercase ASCII identifiers, while empty values and C0,
  C1, or DEL control characters fail with one stable redacted error.
- Provider representations, exceptions, delivery outcomes, logs, events, retry state, history,
  configuration results, and durable state never expose environment keys or secret values.

## [0.7.0] - 2026-08-04

### Added

- ADR-0042 and TS-0025 defining the v0.7 outbound HTTPS webhook adapter, fail-closed
  destination policy, secret-reference authentication, and bounded foreground CLI contract.
- Typed workspace webhook endpoint configuration with strict canonical HTTPS parsing,
  explicit hostname allowlists, bounded timeouts, and fail-closed global-address resolution.
- A single-attempt webhook delivery adapter with canonical size-bounded JSON, fixed identity
  headers, redacted secret material, and stable destination, authentication, transport, and HTTP
  outcome classifications.
- An address-bound standard-library HTTPS transport using validated IP literals with the original
  hostname for platform TLS verification, bounded response reads, and no proxy, redirect, or retry
  behavior.
- A foreground `event deliver` command that selects one named workspace endpoint, enforces a
  100-event maximum, and renders the existing payload-free delivery result in text, JSON, or YAML.

## [0.6.0] - 2026-08-04

### Added

- ADR-0041 and TS-0024 defining the v0.6 bounded local delivery-runner and safe operator CLI
  contracts without introducing a remote transport or background service.
- A transport-neutral one-step and bounded-batch delivery service with typed outcomes,
  deterministic retry profiles, exception redaction, and stale-worker fencing.
- Payload-free durable-event operator commands for idempotent consumer registration and
  inspection, exact retry and abandon targets, and preview-first shared-prefix retention.

## [0.5.0] - 2026-08-04

### Added

- ADR-0040 and TS-0023 defining the v0.5 durable event outbox, ordered at-least-once delivery,
  deterministic retry, operator recovery, and safe retention contracts.
- Schema-versioned SQLite event outbox with immutable redacted envelopes and atomic sequence
  allocation.
- Durable consumer registration, ordered leased claims, acknowledgements, and stale-worker
  rejection backed by the workspace SQLite outbox.
- Subprocess crash-window and multiprocess verification plus fail-closed SQLite integrity and
  symlink boundary checks for durable event state.
- Deterministic bounded delivery retries, exact operator retry and abandon actions, payload-free
  consumer inspection, and preview-first shared-prefix retention.
- An isolated in-process outbox subscriber composed alongside the existing JSONL audit subscriber,
  with independent outbox and execution-history retention lifecycles.

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

# Changelog

All notable changes to Ansiblectl are documented here.

## [Unreleased]

## [0.17.0] - 2026-08-04

### Added

- ADR-0052 and TS-0035 defining a bounded, read-only, single-workspace terminal dashboard.
- The explicit `--workspace PATH dashboard` command with safe status, recent execution, and durable
  consumer panels plus fixed keyboard navigation and manual refresh.
- Deterministic ASCII rendering with field allowlists, governed row limits, terminal-size handling,
  and real pseudo-terminal coverage on Linux and macOS.

### Changed

- Existing read-only application queries are composed into one atomic dashboard snapshot without
  exposing mutation ports or changing existing CLI, machine-output, SDK, history, event, or delivery
  behavior.
- Foreground terminal ownership now uses immediate self-pipe wakeups for resize and interrupt
  signals, with exact terminal restoration and stable interrupted exit behavior.

### Security

- Dashboard output excludes captured output, diagnostics, paths, targeting, revisions, digests,
  payloads, secrets, exceptions, and arbitrary control bytes.
- Terminal preflight fails closed unless input and output are the same supported foreground terminal;
  the dashboard performs no discovery, polling, listening, persistence, or external execution.

## [0.16.0] - 2026-08-04

### Added

- ADR-0051 and TS-0034 defining bounded same-user event delivery to one fixed private workspace
  Unix-domain socket namespace.
- Explicit `event deliver CONSUMER --socket IDENTIFIER --max-events N` selection alongside the
  mutually exclusive HTTPS endpoint and immutable archive adapters.
- Four-byte big-endian framing of canonical event envelopes with exact event-bound acknowledgement
  and EOF validation.

### Changed

- Local process delivery composes with the existing durable consumer ordering, lease, retry,
  exhaustion, and acknowledgement contracts without changing webhook or archive behavior.
- One connection carries one event under a single fixed monotonic deadline; partial I/O is completed
  without adapter-level retry or stream resumption.
- Receiver acknowledgement followed by a process crash remains an explicit at-least-once boundary
  and safely replays the identical stable event identity.

### Security

- Socket identifiers map only below `.ansiblectl/events/sockets/`; private ancestor and socket
  ownership, modes, types, address limits, and pre/post-connect identity are validated fail-closed.
- Linux `SO_PEERCRED` and macOS `getpeereid` bind trust to the connected same-user kernel peer with
  no path, group, privilege, abstract-namespace, timeout, or protocol override.
- Socket identities, paths, peer credentials, payloads, frames, timing details, operating-system
  errors, and exception values remain absent from public results and durable diagnostics.

## [0.15.0] - 2026-08-04

### Added

- ADR-0050 and TS-0033 defining bounded local delivery to immutable workspace-private event
  archives without arbitrary output paths, mutable aggregate files, or background workers.
- Canonical logical archive identifiers and deterministic sequence/event filenames below the fixed
  `.ansiblectl/events/archives/` root.
- Explicit `event deliver CONSUMER --archive ARCHIVE_ID --max-events N` selection alongside the
  existing mutually exclusive HTTPS endpoint adapter.

### Changed

- Durable event envelopes now expose one centralized canonical JSON byte representation shared by
  archive identity, replay validation, and immutable file content.
- Archive delivery reuses the existing consumer ordering, lease, retry, acknowledgement, and
  redacted result contracts without changing webhook behavior or existing outbox databases.
- Exact canonical replay after an archive-write/outbox-ack crash succeeds idempotently without
  rewriting the final file.

### Security

- Archive directories and files are installed with private modes, descriptor-relative custody,
  staging, durable synchronization, and no-overwrite finalization.
- Symlinks, alternate paths, unsafe metadata, conflicting content, partial writes, filesystem
  failures, and same-event races fail closed with a stable redacted outcome.
- Archive identifiers, paths, metadata, payloads, staging details, and filesystem exceptions remain
  absent from public results and durable diagnostic state.

## [0.14.0] - 2026-08-04

### Added

- ADR-0049 and TS-0032 defining optional mutual TLS client authentication for outbound HTTPS
  webhooks without weakening server trust, destination policy, or application authentication.
- Endpoint schema version 6 with paired, distinct workspace-file references for a PEM certificate
  chain and its unencrypted private key.
- In-memory certificate-chain, key-pair, and client-auth usage validation plus an opaque
  request-local identity boundary for the HTTPS transport.

### Changed

- Signed schema v6 endpoints select signature version 1 or 2 explicitly, while schema v5 retains
  its exact v2-only contract and schemas 1 through 4 retain their existing request behavior.
- The HTTPS transport can complete a mutual TLS handshake without persisting client identity
  material or consulting ambient certificate stores.
- Client identity composes independently with bearer authentication, signature v1/v2,
  private-network policy, and platform or exclusive server CA trust.

### Security

- Bearer, signing, certificate, and private-key material resolve and validate before the optional
  clock read, DNS resolution, socket creation, or TLS activity, with no provider, identity,
  anonymous-handshake, or signature-version fallback.
- Missing, malformed, mismatched, unsupported, or unavailable client identity fails with the stable
  redacted `CLIENT_IDENTITY_UNAVAILABLE` outcome before network activity.
- Certificate and key references, PEM material, subjects, issuers, serials, fingerprints, parser
  details, and TLS exceptions remain absent from public results and raw durable retry storage.

## [0.13.0] - 2026-08-04

### Added

- ADR-0048 and TS-0031 defining opt-in timestamp-bound webhook signature v2 without sender nonce
  state, receiver storage, or exactly-once claims.
- Endpoint schema version 5 with fixed `X-Ansiblectl-Timestamp` and v2 signature headers.
- An injected whole-second UTC clock boundary with deterministic tests and a production system-clock
  adapter.

### Changed

- Signature v2 authenticates a fixed domain separator, canonical Unix seconds, and the exact JSON
  body sent by the transport.
- Each at-least-once retry reads a new timestamp and creates a new v2 signature while retaining the
  event identifier, body, and idempotency key.
- Schema versions 1 through 4 retain byte-compatible unsigned and signature-v1 behavior without
  reading the clock.

### Security

- Bearer and signing secrets validate before the single clock read, which validates before DNS,
  socket, TLS, or HTTP activity, with no alternate-clock, v1, or unsigned fallback.
- Signature v2 composes with environment/file custody, private-network policy, and exclusive TLS
  trust as independent controls.
- Timestamp, signature, references, keys, clock details, HMAC state, and transport exceptions remain
  absent from public results, logs, history, retry state, and raw SQLite storage.

## [0.12.0] - 2026-08-04

### Added

- ADR-0047 and TS-0030 defining a fixed workspace-private file secret provider without arbitrary
  paths, configurable roots, provider fallback, or background lifecycle management.
- Exact `file:NAME` routing to `.ansiblectl/secrets/NAME` for bounded webhook bearer authentication
  and HMAC signing alongside unchanged `env:NAME` references.
- Operator guidance and repository exclusion for the private secret namespace.

### Changed

- Webhook delivery now routes each reference to exactly one selected provider and resolves all
  required material before DNS, socket, TLS, or HTTP activity.
- Atomic operator-managed file replacement is observed on the next delivery attempt while an
  in-flight resolution remains bound to its validated descriptor snapshot.

### Security

- Descriptor-relative, no-follow access validates private ownership, permissions, regular-file
  type, single-link custody, device identity, platform capabilities, exact UTF-8 content, and an
  8 KiB bound without trimming or mutation.
- Symlink, directory-replacement, file-replacement, special-file, hard-link, permission, ownership,
  malformed-content, and unsupported-platform paths fail closed with one stable redacted error.
- Secret names, paths, values, metadata, provider details, and exceptions remain absent from public
  results, logs, events, history, retry state, and raw SQLite storage.

## [0.11.0] - 2026-08-04

### Added

- ADR-0046 and TS-0029 defining deterministic HMAC authentication for canonical outbound webhook
  bodies without adding inbound control or arbitrary headers.
- Webhook endpoint schema version 4 with one optional signing-secret reference through the existing
  environment-secret provider boundary.
- A fixed `X-Ansiblectl-Signature` header containing a complete lowercase HMAC-SHA-256 digest over
  a versioned domain separator and the exact transmitted JSON body.

### Changed

- Bounded signing-key resolution and validation now complete before DNS while existing unsigned
  schema versions 1 through 3 retain their exact behavior.
- Unchanged events and effective keys produce stable signatures across intentional at-least-once
  delivery attempts, leaving event-id deduplication and freshness policy to receivers.

### Security

- Missing, malformed, undersized, oversized, control-containing, or exceptional signing material
  fails with `SIGNING_UNAVAILABLE` before network activity and never falls back to unsigned delivery.
- Signing remains independent from bearer authentication, private-network policy, and exclusive TLS
  trust, allowing all positive controls to be composed together.
- Secret references, key material, signature values, HMAC state, provider details, and exceptions
  remain absent from public results, representations, logs, history, events, and durable retry state.

## [0.10.0] - 2026-08-04

### Added

- ADR-0045 and TS-0028 defining bounded, named, exclusive CA trust for outbound HTTPS webhooks.
- Strict workspace trust-policy and canonical PEM bundle loading with no-follow access, ownership,
  permission, size, encoding, certificate-count, and X.509 CA semantic validation.
- Webhook endpoint schema version 3 with one optional immutable TLS trust-policy binding; schema
  versions 1 and 2 remain supported with unchanged platform trust.

### Changed

- A selected custom policy constructs one fresh client TLS context containing only its validated CA
  snapshot while retaining secure runtime TLS and cipher defaults.
- Trust configuration and CA bundles are captured once during command composition, so rotation
  applies only to the next foreground delivery invocation.

### Security

- Exclusive contexts retain mandatory certificate-chain and hostname verification, original DNS
  hostname SNI, and connection to the already validated address tuple without platform-root
  fallback.
- Invalid policies, bundles, certificates, contexts, or handshakes fail closed before or during the
  single transport attempt with stable redacted outcomes.
- Policy identifiers, paths, certificate material and metadata, TLS alerts, and exception details
  remain absent from public and durable delivery surfaces.

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

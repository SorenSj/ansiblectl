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

## Completed milestone

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

## Completed milestone

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
- [x] Restart, crash-window, multiprocess, corruption, and symlink tests pass.
- [x] Retry, abandon, inspection, and retention are deterministic and redaction-safe.
- [x] Existing in-process subscribers and execution-history retention remain compatible.
- [x] The complete quality, build, provenance, and release gates pass.
- [x] Hosted CI passes on Ubuntu and macOS with Python 3.12, 3.13, and 3.14 in
  [PR #18](https://github.com/SorenSj/ansiblectl/pull/18).
- [x] The immutable v0.5.0 tag and
  [tagged artifact workflow](https://github.com/SorenSj/ansiblectl/actions/runs/30865734374) pass
  from merge commit `37d49d4`.

Readiness evidence was last reviewed on 2026-08-04. Version 0.5.0 is released, and its retained
workflow artifact is named `ansiblectl-v0.5.0`; no existing release tag was moved or recreated.

Explicit non-goals:

- Remote delivery protocols, hosted brokers, endpoint credentials, authentication, or tenancy.
- Exactly-once guarantees or distributed transactions with consumer side effects.
- Automatic abandonment, unbounded retries, or using execution history as the outbox.

## Completed milestone

### v0.6.0 — Local event delivery operations

- Bounded application orchestration over the durable consumer claim and acknowledgement contract.
- An injected transport-neutral adapter port with stable redacted outcomes.
- Safe local operator commands for registration, inspection, retry, abandon, and retention.
- Versioned human, JSON, and YAML results without payloads, paths, credentials, or adapter details.

Exit criteria:

- [x] ADR-0041 and TS-0024 define runner, adapter, operator, and output contracts before
  implementation.
- [x] One-step and bounded-batch delivery preserve ordering, leases, retry, and stale-worker safety.
- [x] Operator commands enforce exact targets and preview-first destructive actions.
- [x] Human, JSON, and YAML results are schema-aligned and redaction-safe.
- [x] Existing v0.5 databases and all prior CLI, SDK, event, and history contracts remain compatible.
- [x] The complete quality, build, provenance, and release gates pass.
- [x] Hosted CI passes on Ubuntu and macOS with Python 3.12, 3.13, and 3.14 in
  [PR #23](https://github.com/SorenSj/ansiblectl/pull/23).
- [x] The immutable v0.6.0 tag and
  [tagged artifact workflow](https://github.com/SorenSj/ansiblectl/actions/runs/30867027113) pass
  from merge commit `da58943`.

Readiness evidence was last reviewed on 2026-08-04. Version 0.6.0 is released, and its retained
workflow artifact is named `ansiblectl-v0.6.0`; no existing release tag was moved or recreated.

Explicit non-goals:

- Concrete remote delivery transports, endpoint credentials, authentication, authorization, or
  tenancy.
- Schedulers, daemons, background threads, infinite polling, or automatic recovery actions.
- Exactly-once guarantees, automatic abandon, or automatic retention.

## Completed milestone

### v0.7.0 — Outbound HTTPS webhook delivery

- One outbound HTTPS adapter over the v0.6 transport-neutral delivery port.
- Named workspace endpoint configuration with fail-closed destination policy.
- Optional bearer authentication through the existing secret-reference boundary.
- One explicit bounded foreground delivery command with redacted results.

Exit criteria:

- [x] ADR-0042 and TS-0025 define transport, authentication, destination, lifecycle, and
  compatibility contracts before implementation.
- [x] Endpoint parsing and address-bound connection policy prevent redirect, downgrade, and SSRF
  escape paths.
- [x] Canonical bounded requests and stable response classifications preserve v0.6 retry ownership.
- [x] Secret material remains confined to immediate request construction and never reaches public or
  durable surfaces.
- [x] The bounded CLI command is schema-aligned, foreground-only, and exact-targeted.
- [x] Existing v0.5 databases and v0.6 CLI, SDK, event, history, and runner contracts remain compatible.
- [x] The complete quality, build, provenance, and release gates pass.
- [x] Hosted CI passes on Ubuntu and macOS with Python 3.12, 3.13, and 3.14 in
  [PR #30](https://github.com/SorenSj/ansiblectl/pull/30).
- [x] The immutable v0.7.0 tag and
  [tagged artifact workflow](https://github.com/SorenSj/ansiblectl/actions/runs/30868670698) pass
  from merge commit `e52dea4`.

Readiness evidence was last reviewed on 2026-08-04. Version 0.7.0 is released, and its retained
workflow artifact is named `ansiblectl-v0.7.0`; no existing release tag was moved or recreated.

Explicit non-goals:

- Inbound remote APIs, hosted control planes, tenancy, remote command execution, or a TUI.
- Schedulers, daemons, background threads, service installation, or infinite polling.
- Private-network destinations, redirects, proxies, custom trust stores, mutual TLS, or insecure TLS.
- Arbitrary headers, payload transforms, filters, compression, or additional production secret backends.

## Completed milestone

### v0.8.0 — Environment secret resolution

- One production `env` adapter over the existing secret-provider boundary.
- Exact canonical key lookup without enumeration, fallback, expansion, caching, or persistence.
- Bounded webhook CLI composition with fail-closed authentication before network I/O.
- Stable redacted failures without secret keys, values, environment details, or exception text.

Exit criteria:

- [x] ADR-0043 and TS-0026 define provider identity, key syntax, lookup, lifecycle, composition,
  failure, and redaction contracts before implementation.
- [x] Canonical key validation and exact injected-mapping lookup are implemented.
- [x] Missing, empty, malformed, and invalid material fails with one stable redacted error.
- [x] Authenticated webhook delivery composes the provider while unauthenticated delivery remains
  independent of environment contents.
- [x] Adversarial tests prove keys and values never reach output, logs, exceptions, events, retry
  state, history, configuration results, or durable state.
- [x] Existing v0.5 databases and v0.6/v0.7 CLI, SDK, event, history, endpoint, and runner contracts
  remain compatible.
- [x] The complete local quality, build, provenance, and release gates pass.
- [x] Hosted CI passes on Ubuntu and macOS with Python 3.12, 3.13, and 3.14 in
  [PR #34](https://github.com/SorenSj/ansiblectl/pull/34).
- [x] The immutable v0.8.0 tag and
  [tagged artifact workflow](https://github.com/SorenSj/ansiblectl/actions/runs/30869787997) pass
  from merge commit `9acfcb5`.

Readiness evidence was last reviewed on 2026-08-04. Version 0.8.0 is released, and its retained
workflow artifact is named `ansiblectl-v0.8.0`; no existing release tag was moved or recreated.

Explicit non-goals:

- `.env` files, secret files, keychains, password managers, vaults, cloud secret services, or plugins.
- Command execution, shell expansion, aliases, fallback, discovery, enumeration, mutation, rotation,
  revocation, caching, persistence, or background refresh.
- CLI secret input, interactive prompts, inbound APIs, background delivery, or remote control.

## Completed milestone

### v0.9.0 — Private webhook network policy

- Named workspace policies with bounded canonical RFC 1918 and IPv6 unique-local CIDRs.
- Optional endpoint-to-policy binding while existing endpoints remain global-only.
- All-address validation bound to the exact connected address without a second DNS lookup.
- Stable redacted denial for mixed, forbidden, malformed, or out-of-policy resolution results.

Exit criteria:

- [x] ADR-0044 and TS-0027 define configuration, CIDR, resolution, connection, lifecycle,
  compatibility, and redaction contracts before implementation.
- [x] Strict private-policy parsing rejects unsafe files, ambiguous networks, overlaps, excess
  bounds, unknown fields, and unsupported schemas.
- [x] Endpoint schema version 2 binds at most one named policy while version 1 remains global-only.
- [x] Every resolved address must be allowed, and the connector uses only that validated tuple.
- [x] Loopback, link-local, metadata, mapped, carrier-grade NAT, reserved, and mixed answers remain
  denied without leaking destination or policy detail.
- [x] Existing v0.5 databases and v0.6-v0.8 CLI, SDK, event, history, secret, endpoint, runner, and
  transport contracts remain compatible.
- [x] The complete local quality, build, provenance, and release gates pass.
- [x] Hosted CI passes on Ubuntu and macOS with Python 3.12, 3.13, and 3.14 in
  [PR #39](https://github.com/SorenSj/ansiblectl/pull/39).
- [x] The immutable v0.9.0 tag and
  [tagged artifact workflow](https://github.com/SorenSj/ansiblectl/actions/runs/30870813790) pass
  from merge commit `180d945`.

Readiness evidence was last reviewed on 2026-08-04. Version 0.9.0 is released, and its retained
workflow artifact is named `ansiblectl-v0.9.0`; no existing release tag was moved or recreated.

Explicit non-goals:

- Loopback, link-local, carrier-grade NAT, metadata services, service discovery, Unix sockets, or
  arbitrary private access.
- Combined public/private answers, route-derived trust, DNS suffix trust, or runtime overrides.
- IP-literal URLs, redirects, proxies, custom certificate authorities, pinning, mutual TLS, or
  insecure TLS.
- Background workers, schedulers, daemons, inbound APIs, hosted control planes, or remote commands.

## Completed milestone

### v0.10.0 — Exclusive webhook CA trust

- Named workspace TLS policies referencing bounded CA bundles beneath `.ansiblectl/trust/`.
- Strict X.509 CA validation and immutable one-command trust snapshots.
- Endpoint schema version 3 with exclusive custom trust or unchanged platform trust.
- Mandatory certificate, chain, validity, hostname, and original-hostname SNI verification.

Exit criteria:

- [x] ADR-0045 and TS-0028 define policy, bundle, certificate, endpoint, TLS, lifecycle,
  compatibility, and redaction contracts before implementation.
- [x] Strict trust-policy and bundle loading rejects traversal, unsafe files, permissions, ownership,
  ambiguity, excess bounds, foreign blocks, duplicate certificates, and invalid CA semantics.
- [x] Endpoint schema version 3 binds at most one immutable trust snapshot while versions 1 and 2
  retain platform trust and reject the new field.
- [x] Exclusive contexts load no platform roots and retain `CERT_REQUIRED`, hostname checking,
  original-hostname SNI, and validated-address binding.
- [x] Failures never fall back and expose no policy, path, certificate, or TLS detail.
- [x] Existing v0.5 databases and v0.6-v0.9 CLI, SDK, event, history, secret, endpoint,
  network-policy, runner, and transport contracts remain compatible.
- [x] The complete local quality, build, provenance, and release gates pass.
- [x] Hosted CI passes on Ubuntu and macOS with Python 3.12, 3.13, and 3.14 in
  [PR #45](https://github.com/SorenSj/ansiblectl/pull/45).
- [x] The immutable v0.10.0 tag and
  [tagged artifact workflow](https://github.com/SorenSj/ansiblectl/actions/runs/30872153175) pass
  from merge commit `204b5f2`.

Readiness evidence was last reviewed on 2026-08-04. Version 0.10.0 is released, and its retained
workflow artifact is named `ansiblectl-v0.10.0`; no existing release tag was moved or recreated.

Explicit non-goals:

- Insecure TLS, hostname override, cleartext, TLS downgrade, or trust-on-first-use.
- Supplemental platform trust, platform-store mutation, remote CA retrieval, ACME, or revocation
  service availability guarantees.
- Leaf/SPKI pinning, client certificates, mutual TLS, private keys, hardware tokens, or PKCS#11.
- Redirects, proxies, background workers, inbound APIs, hosted control planes, or remote commands.

## Completed milestone

### v0.11.0 — Signed webhook delivery

- Optional HMAC-SHA-256 authentication over the exact canonical webhook body.
- Existing environment-secret custody with bounded per-attempt signing-key resolution.
- Endpoint schema version 4 with a fixed versioned signature header and no unsigned fallback.
- Stable at-least-once signatures and redacted public and durable surfaces.

Exit criteria:

- [x] ADR-0046 and TS-0029 define endpoint, key, canonical bytes, algorithm, header, lifecycle,
  retry, compatibility, and redaction contracts before implementation.
- [x] Endpoint schema version 4 binds at most one signing-secret reference while versions 1 through
  3 retain exact behavior and reject the new field.
- [x] Fixed vectors prove domain separation, exact-body HMAC-SHA-256, full lowercase digest, and
  fixed header construction.
- [x] Signing and required secret validation complete before DNS with no unsigned or alternate-key
  fallback.
- [x] Signature values, secret references, keys, HMAC state, provider details, and exception text
  remain absent from every public and durable surface.
- [x] Existing v0.5 databases and v0.6-v0.10 CLI, SDK, event, history, secret, endpoint,
  network-policy, TLS-trust, runner, and transport contracts remain compatible.
- [x] The complete local quality, build, provenance, and release gates pass.
- [x] Hosted CI passes on Ubuntu and macOS with Python 3.12, 3.13, and 3.14 in
  [PR #50](https://github.com/SorenSj/ansiblectl/pull/50).
- [x] The immutable v0.11.0 tag and
  [tagged artifact workflow](https://github.com/SorenSj/ansiblectl/actions/runs/30873062409) pass
  from merge commit `2e013af`.

Readiness evidence was last reviewed on 2026-08-04. Version 0.11.0 is released, and its retained
workflow artifact is named `ansiblectl-v0.11.0`; no existing release tag was moved or recreated.

Explicit non-goals:

- Configurable headers, body transforms, content negotiation, compression, or arbitrary signing
  algorithms.
- Asymmetric keys, certificate signing, mutual TLS, client private keys, KMS, HSM, or PKCS#11.
- Sender timestamps, nonce persistence, replay windows, exactly-once delivery, or receiver state.
- Background workers, inbound APIs, hosted control planes, remote commands, or a TUI.

## Most recently completed milestone

### v0.12.0 — Workspace file secret resolution

- One fixed workspace-private `file` adapter over the existing secret-provider boundary.
- Canonical logical names with descriptor-relative, no-follow filesystem validation.
- Exact bounded UTF-8 material without trimming, fallback, caching, or persistence.
- Bounded webhook composition with stable redacted authentication and signing failures.

Exit criteria:

- [x] ADR-0047 and TS-0030 define namespace, filesystem custody, material, routing, lifecycle,
  compatibility, and redaction contracts before implementation.
- [x] Strict name validation and fixed `.ansiblectl/secrets/NAME` resolution are implemented.
- [x] Directory and file ownership, permissions, type, link, device, race, and capability checks
  fail closed before material use.
- [x] Exact bounded material and provider routing operate without enumeration, fallback, trimming,
  caching, mutation, or persistence.
- [x] Bearer and signing composition resolves all required material before network I/O and retains
  existing retry semantics.
- [x] Adversarial tests prove keys, paths, material, metadata, and exception details never reach
  public or durable surfaces.
- [x] Existing endpoint schemas, `env` references, databases, CLI, SDK, event, history, network,
  TLS, runner, and transport contracts remain compatible.
- [x] The complete local quality, build, provenance, and release gates pass.
- [x] Hosted CI passes on Ubuntu and macOS with Python 3.12, 3.13, and 3.14 in
  [release PR #55](https://github.com/SorenSj/ansiblectl/pull/55).
- [x] The immutable v0.12.0 tag and
  [tagged artifact workflow](https://github.com/SorenSj/ansiblectl/actions/runs/30874436512) pass
  from merge commit `1867018`.

Readiness evidence was last reviewed on 2026-08-04. Version 0.12.0 is released, and its retained
workflow artifact is named `ansiblectl-v0.12.0`; no existing release tag was moved or recreated.

Explicit non-goals:

- Arbitrary paths, alternate roots, aliases, enumeration, fallback, permission repair, watching,
  caching, or secret lifecycle management.
- Binary secrets, implicit newline trimming, templates, interpolation, command execution, plugins,
  keychains, vaults, or remote secret services.
- Background workers, inbound APIs, hosted control planes, remote commands, or a TUI.

## Active milestone

### v0.13.0 — Timestamp-bound webhook signatures

- Opt-in signature v2 authenticating canonical Unix seconds and the exact request body.
- Endpoint schema version 5 with fixed timestamp and signature headers.
- One injected clock read per attempt after secret validation and before network activity.
- Receiver-verifiable freshness without sender nonce state or exactly-once claims.

Exit criteria:

- [x] ADR-0048 and TS-0031 define schema, clock, timestamp, canonical bytes, headers, retry,
  compatibility, lifecycle, failure, and redaction contracts before implementation.
- [x] Schema v5 selects signature v2 while schemas 1 through 4 retain exact behavior.
- [x] Fixed vectors prove timestamp bounds, canonical encoding, domain separation, and HMAC bytes.
- [x] All secret and clock validation precedes DNS with no v1, alternate-clock, or unsigned fallback.
- [x] Retries retain event/body/idempotency identity while reading a new timestamp per attempt.
- [x] V2 composes with bearer authentication, env/file custody, network policy, and TLS trust.
- [x] Adversarial tests prove sensitive and request-local signing state never reaches public or
  durable surfaces.
- [x] The complete local quality, build, provenance, and release gates pass.
- [x] Hosted CI passes on Ubuntu and macOS with Python 3.12, 3.13, and 3.14 in
  [release PR #61](https://github.com/SorenSj/ansiblectl/pull/61).
- [ ] The immutable v0.13.0 tag and tagged artifact workflow pass from the release merge commit.

Explicit non-goals:

- Sender nonce persistence, receiver state, replay caches, exactly-once delivery, or clock service
  management.
- Configurable headers, time formats, precision, algorithms, skew, body transforms, or fallbacks.
- Background workers, inbound APIs, hosted control planes, remote commands, or a TUI.

### Future — Additional delivery surfaces

- Additional outbound transports only after each transport's trust and lifecycle contract is accepted.
- A TUI only after its authentication, authorization, tenancy, lifecycle, and compatibility model is
  governed independently from delivery adapters.

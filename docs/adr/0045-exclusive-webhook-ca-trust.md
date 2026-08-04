# ADR-0045: Exclusive Webhook CA Trust

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-04 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0042](0042-outbound-https-webhook-delivery.md), [ADR-0044](0044-private-webhook-network-policy.md), [ADR-0011](0011-security-and-secret-handling.md), [TS-0028](../specifications/ts-0028-exclusive-webhook-ca-trust.md) |

## Context

Version 0.9 permits narrowly approved private webhook destinations but retains platform-only TLS
trust. Many private receivers use an operator-controlled certificate authority. Disabling
verification, accepting arbitrary certificate paths, or silently supplementing platform roots would
turn network reachability into an ambiguous server-identity boundary.

Internal CA support needs a named, reviewable lifecycle that cannot be widened by CLI input and does
not reread mutable files between endpoint composition and connection.

## Decision

Version 0.10 adds named workspace webhook TLS trust policies. Each policy references one canonical
PEM CA bundle beneath `.ansiblectl/trust/`. The bundle is opened without following links, bounded,
parsed before DNS or connection activity, and captured as an immutable in-memory snapshot.

An endpoint schema version 3 document may reference exactly one trust policy. When present, the TLS
context trusts only the validated certificates in that policy; platform roots are not added. When
absent, existing platform trust behavior remains unchanged. Hostname verification, certificate
chain validation, validity checks, and `CERT_REQUIRED` remain mandatory in both modes.

A bundle contains a small bounded set of unique X.509 CA certificates and no private key, leaf
certificate, unknown PEM block, or trailing data. Every certificate must assert CA basic constraints
and, when key usage is present, certificate-signing permission. Policy files, paths, subjects,
issuers, serials, fingerprints, certificate bytes, and TLS exception details do not cross public or
durable boundaries.

The CLI accepts no trust policy, certificate path, certificate bytes, pin, hostname override, or
verification switch. One bounded command binds one endpoint to one immutable trust snapshot; file
rotation takes effect only on a new invocation.

## Consequences

- Private receivers can use operator-controlled CA roots without disabling TLS verification.
- Exclusive trust prevents an internal endpoint policy from also inheriting unrelated platform
  roots.
- Existing endpoint schema versions 1 and 2 retain platform trust and require no migration.
- Operators own CA issuance, secure bundle replacement, overlap during rotation, and expiry.

## Alternatives considered

An `--insecure` switch was rejected because it removes server identity. Adding custom roots to the
platform store was rejected because the effective trust set becomes wider and machine-dependent.
Certificate or SPKI pins were deferred because rotation and chain-change semantics differ from CA
trust. Client certificates were deferred because private-key custody and authentication lifecycle
require a separate decision.

## Compliance

TS-0028 defines policy and bundle configuration, certificate validation, immutable composition,
exclusive TLS context construction, safe outcomes, compatibility, and adversarial verification.
Platform-store mutation, supplemental trust, pinning, mutual TLS, insecure TLS, remote CA retrieval,
or runtime overrides require a separate accepted decision.

# TS-0028: Exclusive Webhook CA Trust

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-04 |
| Related ADRs | [ADR-0045](../adr/0045-exclusive-webhook-ca-trust.md), [ADR-0042](../adr/0042-outbound-https-webhook-delivery.md), [ADR-0044](../adr/0044-private-webhook-network-policy.md) |

## Purpose

Define bounded, named, exclusive CA trust for outbound HTTPS webhooks while preserving mandatory
certificate and hostname verification and existing platform-trust behavior.

## Scope

This specification covers workspace trust-policy configuration, safe CA bundle loading, X.509
validation, endpoint binding, immutable lifecycle, TLS context construction, safe failures, and
compatibility. It does not define client authentication or verification bypasses.

## Trust-policy configuration

Policies live only in `.ansiblectl/webhook-tls-trust.yaml` with schema version 1. The document
contains `policies`, a mapping of at most 32 canonical identifiers. Each policy contains exactly one
`ca_bundle` value: a canonical relative POSIX path beneath `.ansiblectl/trust/` with a `.pem` suffix.

Absolute paths, empty segments, dot segments, backslashes, control characters, non-ASCII text,
components outside the existing identifier character set, and paths longer than 255 bytes are
invalid. Unknown fields, duplicate keys, aliases, anchors, explicit tags, invalid UTF-8, oversized
documents, and unsupported schemas fail closed without echoing identifiers or paths.

The trust directory and bundle MUST NOT be symlinks. The bundle is opened with no-follow semantics,
must be a regular file owned by the current effective user, must not be group- or world-writable,
and is limited to 256 KiB. The resolved target must remain beneath the selected workspace. Files are
read once during composition and never reopened by the connector.

## CA bundle contract

A bundle contains 1 through 16 canonical PEM `CERTIFICATE` blocks separated by one newline and no
other data. Private-key blocks, leaf-only certificates, encrypted material, comments, unknown PEM
labels, duplicate DER certificates, NUL bytes, carriage returns, and non-whitespace trailing bytes
are invalid.

Each block MUST parse as one X.509 certificate and MUST:

- contain a critical basic-constraints extension with `CA=true`;
- permit certificate signing when a key-usage extension is present;
- use a supported public-key and signature algorithm accepted by the runtime TLS implementation;
- be within its declared validity interval at composition time.

The immutable policy snapshot contains only canonical PEM bytes required to construct the context.
Its representation redacts policy identity, path, certificate count, and bytes.

## Endpoint and TLS contract

Webhook endpoint schema version 3 adds optional `tls_trust_policy`. The value must resolve exactly
one named immutable trust snapshot. Schema versions 1 and 2 remain accepted and reject this field.
Version 3 without the field uses the platform trust store exactly as before. Network-policy and TLS
trust-policy selection are independent positive controls.

For a selected trust policy, the connector creates a fresh client TLS context with only the
snapshot's CA certificates. It MUST set `CERT_REQUIRED`, enable hostname checking, send and verify
the endpoint's original canonical DNS hostname, and omit platform default roots. TLS version and
cipher selection retain secure runtime defaults and cannot be configured by workspace or CLI input.

Policy resolution and CA parsing complete before DNS. The context is constructed before opening a
socket. A configuration, parsing, context, certificate, hostname, chain, expiry, or handshake
failure produces the existing redacted configuration or `TRANSPORT_FAILURE` outcome as appropriate;
no fallback to platform trust or a second policy is permitted.

## Lifecycle and safe surfaces

One foreground delivery command captures one immutable trust snapshot and uses it for the entire
bounded batch. It does not watch files, reload after failure, download roots, consult environment
certificate variables, or mutate the platform store. Bundle replacement or rotation applies to the
next invocation only.

Human, JSON, YAML, logs, events, command envelopes, delivery outcomes, retry state, execution
history, and durable state MUST NOT contain policy identifiers, paths, PEM/DER bytes, subjects,
issuers, serials, fingerprints, validity times, certificate counts, TLS alerts, or exception text.

## Compatibility and verification

- Parser tests cover path traversal, unsafe files, permissions, ownership, size, encoding, YAML
  ambiguity, bounds, duplicates, non-CA certificates, key usage, validity, and foreign PEM blocks.
- Fixed certificate fixtures contain no production identity or private key material.
- Endpoint tests prove schema versions 1 and 2 reject the field and version 3 binds exactly one
  immutable policy without changing network-policy behavior.
- Context spies prove exclusive policies do not load default roots, while unbound endpoints retain
  the existing platform context.
- Connector tests prove `CERT_REQUIRED`, hostname checking, original-hostname SNI, validated-address
  binding, no second DNS lookup, no trust fallback, and one snapshot for the complete batch.
- Redaction tests inspect every public and durable surface for sentinel trust and certificate data.
- Existing v0.5 databases and v0.6-v0.9 CLI, SDK, event, history, secret, endpoint, network-policy,
  runner, and transport contracts remain compatible.
- Hosted tests require no public network, private network, or external certificate service.

## Non-goals

- Insecure TLS, hostname override, cleartext, TLS downgrade, or trust-on-first-use.
- Supplemental platform trust, platform-store mutation, remote CA retrieval, ACME, or revocation
  service availability guarantees.
- Leaf/SPKI pinning, client certificates, mutual TLS, private keys, hardware tokens, or PKCS#11.
- Redirects, proxies, background workers, inbound APIs, hosted control planes, or remote commands.

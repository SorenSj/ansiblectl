# TS-0032: Mutual TLS Webhook Client Identity

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-04 |
| Related ADRs | [ADR-0049](../adr/0049-mutual-tls-webhook-client-identity.md), [ADR-0042](../adr/0042-outbound-https-webhook-delivery.md), [ADR-0047](../adr/0047-workspace-file-secret-provider.md) |

## Purpose

Define optional, fail-closed mutual TLS client authentication for outbound HTTPS webhooks without
changing existing server trust, destination, request authentication, or delivery semantics.

## Endpoint contract

Endpoint schema version 6 adds exactly two optional fields:

- `client_certificate_secret`: one `file:NAME` reference containing a PEM certificate chain;
- `client_private_key_secret`: one `file:NAME` reference containing its unencrypted PEM private key.

The fields MUST either both be present or both be absent. Their references MUST be distinct. Empty,
unknown, environment, inline, path, URL, null, and non-string values are invalid. Unsigned schema v6
endpoints remain valid. Schema versions 1 through 5 reject both fields and retain their exact
configuration and request behavior.

Bearer authentication, signature v1 or v2, private-network policy, and platform or exclusive CA
trust remain independently selectable. Client identity does not replace any selected mechanism.

## Material and validation contract

Each reference is resolved through the existing workspace `file` provider and retains TS-0030's
name, type, ownership, permissions, size, UTF-8, no-follow, race, and lifecycle guarantees. Each
material value is resolved exactly once per delivery attempt. No provider fallback or alternate
reference is attempted.

The certificate material MUST contain one or more complete PEM `CERTIFICATE` blocks and no other
block type. The first certificate is the client leaf; following certificates preserve configured
chain order. The key material MUST contain exactly one supported unencrypted PEM private-key block
and no certificate, passphrase, or trailing non-whitespace data. Parsing is bounded and rejects
malformed, unsupported, encrypted, empty, or excessive material.

The leaf certificate's public key MUST match the private key. The certificate MUST permit client
authentication when an Extended Key Usage extension is present. Validity dates and chain issuance
are evaluated by the receiver during TLS; ansiblectl does not invent a local trust decision for its
own certificate.

## Ordering and transport contract

For each attempt, endpoint and body validation precede all secret resolution. Required bearer,
signing, certificate, and private-key materials are then resolved and validated before a v2 clock
read, DNS resolution, socket creation, or TLS activity. No partial identity reaches the transport.

The adapter passes one opaque, request-local identity value to the HTTPS transport. The transport
MUST configure it without writing certificate or key material to a named or temporary filesystem
entry and without consulting ambient client-certificate stores. Server certificate and hostname
validation remain mandatory, redirects and proxies remain disabled, and only the validated target
address may be connected.

If the receiver does not request or accept the configured identity, the TLS attempt fails normally;
there is no second anonymous handshake. The delivery runner remains the sole retry owner.

## Failure, lifecycle, and redaction contract

Missing, unavailable, malformed, mismatched, or unsupported client identity produces only the new
stable delivery outcome `CLIENT_IDENTITY_UNAVAILABLE` before DNS. A TLS-handshake rejection after
network activity retains the existing redacted transport-failure outcome. Neither exposes which
certificate, key, reference, parser, or TLS detail failed.

Resolved material and parsed key objects are request-local and released after the attempt. Secret
references, certificate subjects, issuers, serials, fingerprints, validity dates, PEM labels, public
keys, private keys, parser exceptions, and TLS exceptions MUST NOT appear in command output, logs,
events, history, retry records, configuration results, SQLite, or crash-safe durable state.

## Compatibility and verification

- Schema-pair and provider-restriction tests cover every invalid representation.
- Fixed fixtures cover supported chains and key types, mismatches, encrypted keys, malformed PEM,
  wrong block types, EKU rejection, bounds, and exact provider-call counts.
- Call-order tests prove all required material precedes the optional clock read and all network I/O.
- In-process TLS tests prove a configured receiver accepts the identity, rejects an untrusted one,
  and receives no anonymous fallback attempt.
- Composition tests cover bearer, signature v1/v2, env/file application secrets, public/private
  network policy, and platform/exclusive server trust.
- Raw durable-byte and public-surface tests prove all identity and exception details remain absent.
- Schema versions 1 through 5 retain byte-for-byte requests and never resolve client identity.
- Hosted CI passes on Ubuntu and macOS with Python 3.12, 3.13, and 3.14.

## Non-goals

- Certificate issuance, enrollment, renewal, revocation checking, OCSP, or CA operation.
- Encrypted keys, passphrase references, PKCS#12, SSH keys, hardware keys, agents, KMS, or HSM.
- Environment identities, arbitrary paths, inline PEM, ambient stores, automatic selection, or
  anonymous fallback.
- Receiver authorization, inbound TLS, remote APIs, hosted control planes, background services, or
  a TUI.

# TS-0029: Signed Webhook Delivery

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-04 |
| Related ADRs | [ADR-0046](../adr/0046-signed-webhook-delivery.md), [ADR-0042](../adr/0042-outbound-https-webhook-delivery.md), [ADR-0043](../adr/0043-environment-secret-provider.md) |

## Purpose

Define deterministic optional HMAC authentication for outbound HTTPS webhook bodies while
preserving existing bounded delivery, secret custody, retry, TLS, and redaction contracts.

## Scope

This specification covers endpoint configuration, signing-key resolution, canonical signed bytes,
signature headers, lifecycle, failure classification, compatibility, and safe surfaces. It does not
define receiver implementation, key distribution, freshness policy, or asymmetric signatures.

## Endpoint contract

Webhook endpoint schema version 4 adds optional `signature_secret`. The value is one canonical
secret reference accepted by the existing secret-provider contract. Schema versions 1 through 3
remain accepted and reject this field. Version 4 without the field sends the exact unsigned request
defined by TS-0025.

Signing, bearer authentication, private-network policy, and TLS trust policy are independent
positive controls. A version 4 endpoint may combine them. The CLI accepts no raw key, signature,
algorithm, header name, domain separator, encoding, timestamp, or signing override.

## Key and algorithm contract

For every signed delivery, the configured reference is resolved exactly once before DNS. Revealed
material is encoded as UTF-8 and MUST contain 32 through 256 bytes. Empty, undersized, oversized,
control-containing, unavailable, or exceptional material fails with `SIGNING_UNAVAILABLE`.

The only algorithm is HMAC-SHA-256. Implementations MUST use the standard-library HMAC primitive
and MUST NOT truncate the digest. Keys are not cached, persisted, logged, returned, compared,
enumerated, expanded, or reused for an unsigned fallback.

## Canonical signature contract

The input is exactly:

```text
ASCII("ansiblectl-webhook-signature-v1\n") || canonical_request_body
```

`canonical_request_body` is the exact bounded JSON byte sequence sent by TS-0025, without
re-encoding, whitespace changes, newline addition, header inclusion, or content transformation.
The output header is exactly:

```text
X-Ansiblectl-Signature: v1=<64 lowercase hexadecimal characters>
```

The header is added only after successful key validation and signing. Existing fixed content type,
event identity, sequence, idempotency, and user-agent headers remain unchanged. Header names or
values cannot be configured.

## Ordering, retry, and failure contract

Payload size validation and all required secret resolution complete before DNS. Signing completes
before destination resolution and transport construction. A signing failure performs no DNS,
socket, or transport activity and produces only `SIGNING_UNAVAILABLE`.

One delivery attempt computes at most one signature. A bounded retry of the same immutable event
uses the same canonical body and produces the same HMAC when the effective key is unchanged. Key
rotation applies at the next secret resolution and may therefore change a later attempt; the
receiver remains responsible for idempotency by signed event identifier and for any freshness or
replay-window policy.

Transport and HTTP failures retain existing classifications. No failure retries signing inside one
adapter attempt, removes the signature, switches keys, sends unsigned, or exposes exception text.

## Lifecycle and safe surfaces

Signing material exists only during immediate key validation, HMAC calculation, and request
construction. Request representations may expose the fixed header name but never its value. Human,
JSON, YAML, logs, events, command envelopes, delivery outcomes, retry state, execution history,
durable state, and exceptions MUST NOT contain the secret reference, key material, signature value,
intermediate HMAC state, provider details, or signing exception text.

## Compatibility and verification

- Endpoint tests prove schemas 1 through 3 reject `signature_secret` and schema 4 binds at most one
  exact secret reference without changing network or TLS policy behavior.
- Fixed vectors prove the domain separator, exact canonical body, complete SHA-256 digest, lowercase
  hexadecimal encoding, and fixed header syntax.
- Ordering spies prove payload bounds and signing complete before DNS and that failures perform no
  resolver or transport calls.
- Retry tests prove one HMAC per attempt and deterministic signatures for unchanged event and key.
- Adversarial redaction tests inspect public, logging, history, event, retry, and durable surfaces.
- Existing v0.5 databases and v0.6-v0.10 CLI, SDK, event, history, secret, endpoint, network-policy,
  TLS-trust, runner, and transport contracts remain compatible.
- Hosted verification requires no public network, receiver, certificate service, or external secret
  provider.

## Non-goals

- Encryption, bearer-token replacement, TLS replacement, mutual TLS, or client certificates.
- Asymmetric signatures, key identifiers, algorithm negotiation, digest truncation, or key download.
- Configurable headers, signed header sets, body templates, compression, transforms, or content types.
- Sender-managed nonce databases, timestamps, replay windows, clock synchronization, or exactly-once
  delivery.
- Secret files, `.env` files, keychains, vaults, cloud KMS, HSM, PKCS#11, remote APIs, or background
  workers.

# TS-0031: Timestamp-Bound Webhook Signatures

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-04 |
| Related ADRs | [ADR-0048](../adr/0048-timestamp-bound-webhook-signatures.md), [ADR-0046](../adr/0046-signed-webhook-delivery.md) |

## Purpose

Define an opt-in HMAC signature version that authenticates one canonical request-attempt timestamp
alongside the exact webhook body without changing existing signature v1 delivery.

## Endpoint contract

Endpoint schema version 5 adds exactly one field, `signature_version`. Its only accepted value is
the integer `2`; booleans, strings, other integers, and null are invalid. The field requires an
existing `signature_secret`. A schema v5 signed endpoint requires `signature_version: 2`; unsigned
schema v5 endpoints omit both fields. Schema versions 1 through 4 reject `signature_version` and
retain their exact configuration, request, and retry behavior.

Bearer authentication, environment or file secret custody, private-network policy, and exclusive
TLS trust remain independently selectable and compose without precedence changes.

## Clock and timestamp contract

The adapter receives an injected clock port. One v2 attempt calls it exactly once after endpoint,
payload, bearer material, and signing material validation, and before destination resolution or
transport construction. The production clock returns an integer UTC Unix second. Tests inject fixed
or failing clocks; no test depends on ambient wall time.

Accepted values are integers from `0` through `253402300799` inclusive. Booleans, floats, decimal
strings, negative values, excess values, and exceptions are invalid. The canonical timestamp is the
base-10 ASCII representation with no sign, whitespace, decimal point, exponent, or leading zero
except the value `0`.

Unsigned and signature-v1 endpoints MUST NOT call or require a clock.

## Canonical signature and request contract

The exact HMAC-SHA-256 input is:

```text
ansiblectl-webhook-signature-v2\n<TIMESTAMP>\n<BODY>
```

The domain separator and timestamp are ASCII bytes. `BODY` is the exact canonical JSON byte string
sent by the transport; it is neither decoded nor reconstructed. The signing key retains TS-0029's
material bounds and custody rules.

The adapter adds exactly these fixed headers:

- `X-Ansiblectl-Timestamp: <TIMESTAMP>`
- `X-Ansiblectl-Signature: v2=<64 lowercase hexadecimal characters>`

Operators cannot override either header. V2 never emits `v1=`, alternate algorithms, multiple
signatures, or an unsigned request.

## Retry, failure, and lifecycle contract

Every at-least-once delivery attempt resolves its required material and reads the clock anew. The
same event and key with the same timestamp produce identical signatures. A later timestamp produces
a different signature while the body, event identifier, and `Idempotency-Key` remain stable.

Clock or signing failure produces only `SIGNING_UNAVAILABLE`, performs no DNS, socket, TLS, or HTTP
activity, and does not consume an alternate timestamp, key, signature version, or unsigned fallback.
The existing runner owns bounded retry scheduling and acknowledgement exactly as before.

The timestamp and signature are request-local. Neither is written to event payloads, results, logs,
history, retry state, command envelopes, configuration results, or SQLite. Secret references, key
material, clock exceptions, and internal HMAC state retain existing redaction guarantees.

## Compatibility and verification

- Fixed vectors cover timestamp boundaries, canonical decimal encoding, exact v2 signed bytes, and
  full lowercase digest construction.
- Invalid clock types, ranges, and exceptions fail before resolver or transport calls.
- Call-order tests prove all required secrets precede the single clock read, which precedes DNS.
- Retry tests prove timestamp/signature changes and stable body/event/idempotency identity.
- Schema versions 1 through 4 retain byte-for-byte request behavior and never invoke the clock.
- V2 composes with bearer authentication, both production secret providers, private-network policy,
  platform or exclusive CA trust, and bounded runner outcomes.
- Human, JSON, YAML, logs, events, history, retry records, and raw durable bytes contain no key,
  secret reference, signature, timestamp, clock detail, or exception text.
- Hosted CI passes on Ubuntu and macOS with Python 3.12, 3.13, and 3.14.

## Receiver guidance

Receivers SHOULD compare the authenticated timestamp with a documented UTC clock and a deliberately
bounded skew window, then deduplicate the authenticated event identifier. Timestamp validation
without receiver state does not prevent replay. Receiver policy and storage are not sender
configuration and are not an ansiblectl exactly-once guarantee.

## Non-goals

- Configurable header names, timestamp formats, precision, algorithms, domain separators, or skew.
- Sender nonce generation or persistence, receiver storage, replay caches, challenge-response, or
  exactly-once delivery.
- Clock synchronization, NTP management, clock correction, fallback clocks, or background refresh.
- Body transforms, redirects, proxies, inbound APIs, hosted control planes, remote commands, or a
  TUI.

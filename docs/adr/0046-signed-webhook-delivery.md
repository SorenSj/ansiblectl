# ADR-0046: Signed Webhook Delivery

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-04 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0042](0042-outbound-https-webhook-delivery.md), [ADR-0043](0043-environment-secret-provider.md), [ADR-0011](0011-security-and-secret-handling.md), [TS-0029](../specifications/ts-0029-signed-webhook-delivery.md) |

## Context

HTTPS authenticates the receiver and protects bytes in transit, but it does not give a receiver an
application-level proof that a webhook body was produced by its configured ansiblectl sender.
Receivers commonly need to authenticate deliveries across TLS termination boundaries and reject
modified payloads without granting ansiblectl new inbound or remote-control capabilities.

Arbitrary configurable headers, ad hoc templates, raw CLI secrets, or signatures over a
noncanonical representation would create ambiguous security and compatibility boundaries. Replay
prevention also cannot be promised by a stateless sender with intentional at-least-once retries.

## Decision

Version 0.11 adds optional HMAC-SHA-256 signing to webhook endpoint schema version 4. An endpoint
references one signing secret through the existing secret-provider contract. The secret is resolved
immediately for one delivery, validated as a bounded key, used only to sign the exact canonical JSON
body, and discarded with the request operation.

The signed bytes are the ASCII domain separator `ansiblectl-webhook-signature-v1`, one newline, and
the exact request body. The fixed `X-Ansiblectl-Signature` header contains `v1=` followed by the
lowercase hexadecimal HMAC. The signed body already contains the immutable event identifier,
sequence, occurrence time, name, operation identifier, payload, and schema version.

Signing is an independent positive control from bearer authentication, destination policy, and TLS
trust. A configured signing secret that is missing, malformed, or unavailable fails before DNS and
transport with one stable redacted outcome. There is no unsigned fallback. Schema versions 1
through 3 reject the new field and retain their exact behavior.

At-least-once retry sends the same canonical body and therefore the same signature. Receivers use
the signed event identifier for idempotency and own freshness or replay-window policy. Signature
values, secret references, secret material, intermediate HMAC state, and provider exceptions never
cross public, logging, history, event, retry, or durable-state boundaries.

## Consequences

- Receivers can authenticate canonical webhook bytes independently of TLS termination.
- Existing environment-secret custody and fail-closed composition are reused without new secret
  files, CLI inputs, or persistence.
- Receivers must implement constant-time HMAC comparison and event-id deduplication.
- Signing provides authenticity and integrity, not confidentiality or sender non-repudiation.

## Alternatives considered

Asymmetric signatures were deferred because private-key custody, algorithm agility, and public-key
distribution require a separate lifecycle. Signing arbitrary headers was rejected because
intermediaries normalize them inconsistently. A timestamp-only replay scheme was rejected because
clock policy belongs to the receiver and retries are intentionally stable. Mutual TLS was deferred
because client private-key handling requires a separate accepted decision.

## Compliance

TS-0029 defines endpoint binding, canonical signed bytes, key bounds, header format, lifecycle,
failure behavior, compatibility, redaction, and deterministic verification. Arbitrary signing
algorithms, configurable headers, secret files, remote key services, asymmetric keys, mutual TLS,
or sender-managed replay state require a separate accepted decision.

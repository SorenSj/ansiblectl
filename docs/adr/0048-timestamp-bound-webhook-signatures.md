# ADR-0048: Timestamp-Bound Webhook Signatures

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-04 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0046](0046-signed-webhook-delivery.md), [ADR-0047](0047-workspace-file-secret-provider.md), [TS-0031](../specifications/ts-0031-timestamp-bound-webhook-signatures.md) |

## Context

Version 0.11 authenticates the canonical webhook body with a deterministic HMAC. An unchanged
event and key intentionally produce the same signature on every at-least-once attempt. Receivers
can deduplicate the stable event identifier, but the signature alone provides no authenticated
statement about when a particular request attempt was created.

Freshness must not be confused with exactly-once delivery. A sender timestamp can support a
receiver-defined acceptance window, but only receiver state can reject a previously accepted event.
Clock access also introduces failure, range, precision, retry, and testing contracts that cannot be
added implicitly to the existing v1 signature.

## Decision

Version 0.13 adds an opt-in timestamp-bound signature v2 through endpoint schema version 5. A v2
endpoint retains one `signature_secret` and explicitly selects `signature_version: 2`. It sends one
fixed `X-Ansiblectl-Timestamp` header containing canonical decimal Unix seconds and one fixed
`X-Ansiblectl-Signature` header containing `v2=` plus the full lowercase HMAC-SHA-256 digest.

The signed bytes are a fixed ASCII v2 domain separator, newline, the exact timestamp header bytes,
newline, and the exact canonical JSON body. The injected clock is read exactly once per adapter
attempt after all required secret material is validated and before DNS. Fractional time is rejected
rather than rounded. Each retry reads the clock again, so its timestamp and signature may change
while its event identifier and body remain stable.

Clock failure, invalid range or representation, signing failure, or missing material maps to the
existing `SIGNING_UNAVAILABLE` outcome before network activity. There is no fallback to v1 or
unsigned delivery. Schema versions 1 through 4 keep their exact current behavior and never read the
clock.

## Consequences

- Receivers can authenticate request-attempt time and apply their own explicit skew window.
- Receivers still need event-id deduplication or equivalent state to prevent replay within or across
  acceptance windows.
- At-least-once retries no longer have stable v2 signature bytes, although their body and
  `Idempotency-Key` remain stable.
- Deterministic injected clocks keep tests independent from wall time.

## Alternatives considered

Reusing the event's `occurred_at` was rejected because queued events may be delivered much later
and it describes event creation, not request creation. Milliseconds and formatted timestamps were
rejected because they add precision and canonicalization ambiguity. Replacing v1 in place was
rejected as a compatibility break. Nonces were rejected because meaningful replay prevention would
require receiver state and sender persistence. A configurable header or algorithm was rejected to
preserve the fixed request contract.

## Compliance

TS-0031 defines schema selection, clock behavior, canonical bytes, headers, retry behavior,
compatibility, failure mapping, redaction, and verification. Sender-side nonce persistence,
receiver state, exactly-once claims, and configurable replay policy remain out of scope.

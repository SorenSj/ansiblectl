# ADR-0042: Outbound HTTPS Webhook Delivery

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-04 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0041](0041-local-event-delivery-runner.md), [ADR-0030](0030-remote-api-deferral.md), [ADR-0028](0028-workspace-lifecycle-and-isolation.md), [TS-0025](../specifications/ts-0025-outbound-https-webhook-delivery.md) |

## Context

Version 0.6 established bounded delivery orchestration and a narrow transport-neutral adapter port.
The next useful integration is outbound delivery to an operator-controlled HTTPS webhook. A naive
HTTP client would create credential leakage, redirect, TLS downgrade, DNS rebinding, server-side
request forgery, response disclosure, and unbounded-resource risks.

This decision concerns an outbound adapter only. It does not revise ADR-0030 or introduce an
inbound API, hosted control plane, tenant service, scheduler, or daemon.

## Decision

Version 0.7 introduces one standard outbound HTTPS webhook adapter. An endpoint is selected by a
canonical local identifier and resolved from the selected workspace's typed configuration. The CLI
does not accept a URL, header, token, or secret value. Optional authentication uses a
`SecretReference`; material is resolved only immediately before the request and is never placed in
configuration results, events, durable state, diagnostics, or command output.

Every endpoint must use canonical `https` with no user information, fragment, non-canonical host,
or ambiguous port. Configuration contains an explicit hostname allowlist. Resolution must reject
loopback, link-local, multicast, unspecified, reserved, and private addresses unless a future ADR
defines a separately named private-network policy. Every connected address must remain allowed.
Redirects are disabled. Certificate and hostname validation use the platform trust store and
cannot be disabled by configuration or CLI flags.

The adapter sends the immutable redacted event envelope as canonical JSON with a bounded body,
fixed content type, user agent, event identity headers, and the event identifier as the idempotency
key. It uses explicit connect/read timeouts, bounded response reads, no ambient proxy or credential
discovery, and no automatic retry. The v0.6 runner remains the sole retry owner.

One explicit command, `event deliver CONSUMER --endpoint NAME --max-events N`, composes the endpoint,
secret provider, adapter, retry profile, and v0.6 runner. It remains bounded, foreground-only, and
workspace-scoped. Machine and human results reuse the v0.6 payload-free delivery result.

## Consequences

- Operators can deliver redacted public events to a controlled HTTPS receiver without exposing
  transport details to the application service.
- Endpoint trust and network policy fail closed before a request.
- Receivers can deduplicate at-least-once attempts with the stable event identifier.
- A production secret-provider adapter is required before authenticated delivery can be composed.
- Private-network webhooks, proxies, custom certificate authorities, and mutual TLS remain
  unavailable until separately governed.

## Alternatives considered

Accepting arbitrary URLs and bearer tokens on the CLI was rejected because process listings,
shell history, logs, and command envelopes can retain them. Automatic redirects were rejected
because they can escape the reviewed destination. Automatic HTTP retries were rejected because
they would obscure the durable runner's attempt accounting. A general inbound remote API was
rejected because authentication, authorization, tenancy, lifecycle, and compatibility remain
outside this outbound integration.

## Compliance

TS-0025 defines endpoint validation, request construction, outcome classification, CLI behavior,
redaction, and adversarial verification. Any inbound listener, background service, private-network
policy, proxy support, custom trust store, mutual TLS, or new secret backend requires a separate
decision before implementation.

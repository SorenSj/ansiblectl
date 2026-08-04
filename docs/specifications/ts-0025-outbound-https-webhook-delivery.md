# TS-0025: Outbound HTTPS Webhook Delivery

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-04 |
| Related ADRs | [ADR-0042](../adr/0042-outbound-https-webhook-delivery.md), [ADR-0041](../adr/0041-local-event-delivery-runner.md), [ADR-0030](../adr/0030-remote-api-deferral.md), [ADR-0011](../adr/0011-security-and-secret-handling.md) |

## Purpose

Define a fail-closed outbound HTTPS webhook adapter and bounded foreground CLI composition over the
v0.6 durable delivery runner.

## Scope

This specification covers typed endpoint configuration, destination policy, optional bearer-secret
resolution, canonical request construction, response classification, bounded I/O, CLI invocation,
safe results, and compatibility. It does not define an inbound API or background service.

## Endpoint contract

An endpoint definition contains only:

- canonical endpoint identifier;
- absolute HTTPS URL;
- non-empty explicit allowed-hostname set containing the URL hostname;
- optional `SecretReference` for bearer authentication;
- positive connect and read timeouts within implementation-defined public maxima;
- schema version 1.

The URL MUST contain a canonical DNS hostname and MAY contain a path, query, and explicit port.
User information, fragments, IP-literal hosts, Unicode ambiguity, control characters, and schemes
other than `https` are invalid. Endpoint identifiers and hostnames are compared after documented
canonicalization. Duplicate endpoint identifiers fail configuration resolution.

CLI arguments identify an endpoint by name. They MUST NOT accept URLs, headers, secret references,
secret values, proxy settings, certificate overrides, or retry timing.

## Destination and transport policy

Before each connection, every resolved address for the canonical hostname MUST be globally
routable and MUST NOT be loopback, link-local, multicast, unspecified, reserved, or private.
Connection establishment MUST remain bound to an address from that validated resolution result;
validation followed by an unrelated resolver lookup is forbidden. A resolution change or mixed
allowed/disallowed result fails closed as `DESTINATION_DENIED`.

Redirect following, ambient proxy discovery, ambient HTTP authentication, cleartext fallback,
certificate-validation disablement, hostname-validation disablement, and unbounded response reads
are forbidden. TLS uses the platform trust store. Connect and read phases use their configured
bounds, and the response body is discarded after a small fixed maximum sufficient for protocol
cleanup. Response bodies and headers never enter delivery outcomes or diagnostics.

## Secret handling

Optional bearer authentication is represented only by `SecretReference`. The composition root
resolves it through `SecretService` for the immediate request. The adapter adds exactly one
`Authorization: Bearer` header after rejecting control characters in the revealed material.
Secret material MUST NOT appear in object representations, exceptions, logs, durable failure
state, event payloads, command output, URLs, or build/test fixtures committed to the repository.

Missing, denied, malformed, or unavailable secret material fails before network I/O and maps to
`AUTHENTICATION_UNAVAILABLE`. Public results contain only that stable reason.

## Request contract

For each delivery attempt the adapter sends one `POST` request whose body is the envelope's
canonical compact JSON representation encoded as UTF-8. The body has a documented maximum size;
oversized envelopes fail before network I/O as `PAYLOAD_TOO_LARGE`.

Fixed headers are:

- `Content-Type: application/json`;
- `User-Agent: ansiblectl-webhook/<major-schema>`;
- `Idempotency-Key: <event_id>`;
- `X-Ansiblectl-Event-Id: <event_id>`;
- `X-Ansiblectl-Event-Sequence: <sequence>`;
- optional bearer authorization from the secret boundary.

Operators cannot add or override headers. The adapter performs no retry; one call produces one
request attempt at most.

## Outcome classification

The adapter returns the existing `DeliveryOutcome` with no transport detail:

- HTTP 200 through 299: delivered;
- HTTP 408, 425, 429, and 500 through 599: `REMOTE_RETRYABLE`;
- other HTTP statuses: `REMOTE_REJECTED`;
- connect, DNS, TLS, timeout, truncated-protocol, or bounded-read failure: `TRANSPORT_FAILURE`;
- destination-policy rejection: `DESTINATION_DENIED`;
- secret resolution failure: `AUTHENTICATION_UNAVAILABLE`;
- locally oversized envelope: `PAYLOAD_TOO_LARGE`.

Status codes, reason phrases, response headers, bodies, resolved addresses, hostnames, URLs,
certificate details, and exception text MUST NOT cross the adapter port. Unexpected implementation
exceptions retain the v0.6 runner's `ADAPTER_FAILURE` mapping.

## CLI and lifecycle

The public command is:

`event deliver CONSUMER --endpoint NAME --max-events N`

`N` is a positive integer with a documented finite maximum. The command resolves exactly one
workspace, endpoint, registered consumer, secret provider, retry profile, and adapter. It invokes
the v0.6 bounded runner once in the foreground and then exits. It never sleeps, polls indefinitely,
spawns, daemonizes, installs a service, automatically abandons, or automatically retains events.

Human, JSON, and YAML reuse `DeliveryRunResult` schema version 1. Results contain no payload,
endpoint identifier, URL, hostname, address, secret reference, credential, HTTP status, header,
response content, or exception text. Existing typed configuration, state, secret, and delivery
errors retain their registered public codes and exit behavior.

## Compatibility and verification

- Endpoint parsing rejects every forbidden URL component and ambiguous hostname form.
- Deterministic resolver and connector fakes prove address validation remains bound to connection.
- Redirect, proxy, certificate-disablement, and ambient-credential paths are absent or rejected.
- Request tests prove canonical bytes, fixed headers, size bound, and exactly one attempt.
- Classification tests cover every status family and transport failure without leaking details.
- Secret tests prove resolution occurs immediately before I/O and values never reach representations,
  logs, results, durable state, or captured exceptions.
- CLI tests prove exact endpoint selection, positive bounded counts, foreground termination, and
  schema-aligned redacted human, JSON, and YAML output.
- Existing v0.5 databases, v0.6 runner behavior, CLI commands, SDK imports, event schemas, execution
  history, and exit codes remain compatible.
- The supported Python and operating-system CI matrix passes without requiring public network access.

## Non-goals

- Inbound REST, RPC, webhook listeners, hosted APIs, tenancy, or remote command execution.
- Background workers, schedulers, daemons, service installation, or automatic recovery.
- Private, loopback, link-local, Unix-socket, or service-discovery destinations.
- Redirects, proxies, custom certificate authorities, certificate pinning, mutual TLS, or insecure TLS.
- Arbitrary headers, payload transforms, event filtering, compression, streaming, or batch HTTP bodies.
- Additional production secret-provider backends; those require their own lifecycle and trust decision.

# ADR-0044: Private Webhook Network Policy

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-04 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0042](0042-outbound-https-webhook-delivery.md), [ADR-0028](0028-workspace-lifecycle-and-isolation.md), [TS-0025](../specifications/ts-0025-outbound-https-webhook-delivery.md), [TS-0027](../specifications/ts-0027-private-webhook-network-policy.md) |

## Context

Version 0.7 deliberately restricts webhook destinations to globally routable addresses. This is a
safe default but prevents delivery to operator-controlled receivers on private automation networks.
A general `allow_private` switch would collapse the SSRF boundary and could expose loopback,
link-local, metadata, service-discovery, or unrelated internal services after DNS changes.

Private delivery therefore needs a separately governed, positive destination policy whose reviewed
scope cannot be widened by CLI input or ambient network configuration.

## Decision

Version 0.9 adds named workspace webhook network policies in a separate typed private configuration
document. An endpoint may reference exactly one policy by canonical identifier. A policy contains a
small bounded set of canonical CIDR networks, each wholly contained in an RFC 1918 IPv4 range or an
IPv6 unique-local range. Existing endpoints without a policy retain the v0.7 global-only behavior.

Every address returned for the endpoint hostname must belong to one of the selected policy's exact
ranges. Mixed allowed and disallowed answers fail closed. Loopback, link-local, multicast,
unspecified, reserved, documentation, benchmark, carrier-grade NAT, IPv4-mapped IPv6, and metadata
addresses remain denied even when a broader input range would appear to contain them. Connection
establishment remains bound to one address from the validated answer set.

The URL still requires a canonical DNS hostname and HTTPS. Redirects, proxies, ambient credentials,
custom trust stores, certificate bypass, and CLI destination overrides remain forbidden. The
platform trust store and original DNS hostname continue to provide TLS verification; a private
policy grants network reachability only, never server identity trust.

## Consequences

- Operators can explicitly authorize narrow private receiver networks without enabling arbitrary
  private-network access.
- Policy names and CIDRs are private configuration inputs and never appear in delivery results,
  durable failure state, logs, or events.
- Existing public endpoint documents remain valid and keep their original fail-closed policy.
- Operators must provision a certificate trusted by the platform for the endpoint hostname.

## Alternatives considered

A boolean `allow_private` option was rejected because it has no reviewable scope. Endpoint-local
CIDRs were rejected because duplicated trust policy drifts across endpoints. URL IP literals were
rejected because they weaken hostname identity and certificate verification. Custom certificate
authorities and pinning were deferred because their storage, rotation, and failure lifecycle need a
separate decision.

## Compliance

TS-0027 defines policy configuration, CIDR canonicalization, address classification, endpoint
binding, safe failures, compatibility, and adversarial verification. Broader address classes,
service discovery, custom trust, proxies, Unix sockets, or runtime policy overrides require a
separate accepted decision.

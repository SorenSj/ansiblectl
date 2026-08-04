# TS-0027: Private Webhook Network Policy

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-04 |
| Related ADRs | [ADR-0044](../adr/0044-private-webhook-network-policy.md), [ADR-0042](../adr/0042-outbound-https-webhook-delivery.md), [ADR-0028](../adr/0028-workspace-lifecycle-and-isolation.md) |

## Purpose

Define a positive, named, CIDR-bounded policy for outbound HTTPS webhook delivery to explicitly
approved private networks without weakening the v0.7 public-destination default.

## Scope

This specification covers workspace policy configuration, canonical identifiers and networks,
endpoint references, resolution evaluation, address-bound connection behavior, redacted failures,
and compatibility. It does not define server identity overrides or a general private-network mode.

## Configuration contract

Private policies live only in `.ansiblectl/webhook-network-policies.yaml` with schema version 1.
The document contains `policies`, a mapping of at most 32 canonical policy identifiers. Each policy
contains only `allowed_cidrs`, a non-empty list of at most 16 unique canonical CIDR strings.
Unknown fields, duplicate YAML keys, aliases, tags, invalid UTF-8, symlinks, non-regular files,
oversized documents, and unsupported schema versions fail configuration resolution.

Policy identifiers use the existing endpoint-identifier grammar. A CIDR is canonical only when its
text equals the standard compressed network representation, includes an explicit prefix, has no
zone identifier, and is wholly contained in one of:

- `10.0.0.0/8`;
- `172.16.0.0/12`;
- `192.168.0.0/16`;
- `fc00::/7`.

Host-bit coercion, implicit masks, IPv4-mapped IPv6, carrier-grade NAT, documentation, benchmark,
reserved, loopback, link-local, multicast, and unspecified ranges are invalid. Overlapping or
redundant entries within one policy are rejected rather than normalized silently.

Webhook endpoint schema version 2 adds one optional `network_policy` identifier. When present it
must resolve exactly one named policy. Schema version 1 remains accepted and always uses the v0.7
global-only policy. Version 2 without `network_policy` also uses the global-only policy. The CLI
accepts neither policy names nor CIDRs.

## Resolution and connection contract

The selected policy is resolved before DNS activity. For a private-policy endpoint, every canonical
address in the one resolution result MUST:

- have the same address family semantics as its parsed form, with mapped forms rejected;
- be neither loopback, link-local, multicast, unspecified, nor reserved;
- belong to at least one exact allowed CIDR in the selected policy.

An empty result, malformed address, mixed allowed/disallowed result, address outside the selected
ranges, or policy/configuration change fails closed as `DESTINATION_DENIED`. No subset is selected
from a mixed answer. Global addresses are denied for a private-policy endpoint unless a future
contract defines an explicit combined policy.

The connector receives only the immutable validated address tuple and must connect to one member
without resolving the hostname again. TLS sends and verifies the original canonical hostname.
Redirects remain disabled, so a response cannot change the reviewed destination.

## Lifecycle and safe surfaces

Policy configuration is read once during bounded foreground command composition. One command binds
one endpoint to one immutable policy snapshot. It does not watch files, reload during a batch,
discover routes, inspect interfaces, or derive permissions from DNS suffixes or search domains.

Public and durable surfaces reuse `DESTINATION_DENIED` and MUST NOT contain policy identifiers,
CIDRs, resolved addresses, endpoint identifiers, hostnames, URLs, resolver details, or exception
text. Configuration diagnostics identify only the safe document class and stable correction action;
they do not echo rejected CIDRs or policy names.

## Compatibility and verification

- Fixed vectors cover canonical/private network boundaries for IPv4 and IPv6.
- Parser tests reject host bits, mapped addresses, forbidden ranges, overlaps, excess bounds,
  duplicate keys, unknown fields, unsafe files, and unsupported schemas.
- Resolver fakes cover all-allowed, all-denied, mixed, empty, malformed, and changing answers.
- Connector tests prove the connected address comes from the validated tuple and no second lookup
  occurs while TLS retains the original hostname.
- Redaction tests prove policies, CIDRs, addresses, hostnames, URLs, and exception values never
  reach human, JSON, YAML, logs, events, delivery outcomes, retry state, history, or durable state.
- Existing schema-version-1 endpoint files remain byte-for-byte behaviorally global-only.
- Existing v0.5 databases and v0.6-v0.8 CLI, SDK, event, history, secret, endpoint, runner, and
  transport contracts remain compatible.
- The supported Python and operating-system CI matrix passes without public or private network I/O.

## Non-goals

- Loopback, link-local, carrier-grade NAT, metadata services, service discovery, Unix sockets, or
  arbitrary private access.
- Combined public/private answers, route-derived trust, DNS suffix trust, or runtime overrides.
- IP-literal URLs, redirects, proxies, custom certificate authorities, pinning, mutual TLS, or
  insecure TLS.
- Background workers, schedulers, daemons, inbound APIs, hosted control planes, or remote commands.

# ADR-0051: Workspace Unix Socket Delivery

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-04 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0040](0040-durable-event-outbox.md), [ADR-0041](0041-local-event-delivery-runner.md), [ADR-0028](0028-workspace-lifecycle-and-isolation.md), [TS-0034](../specifications/ts-0034-workspace-unix-socket-delivery.md) |

## Context

The durable runner now delivers through hardened HTTPS and immutable archive adapters. Local
process integrations still lack a bounded streaming surface: polling archive directories adds a
second lifecycle, while TCP, arbitrary socket paths, stdout pipes, commands, and plugins expand the
destination or execution trust boundary.

A Unix-domain socket can remain inside the private workspace namespace and avoids DNS, IP routing,
TLS, proxies, and network credentials. It still requires explicit contracts for path custody,
socket replacement, peer identity, message framing, acknowledgement, timeouts, partial I/O, and
receiver lifecycle. Successful `connect()` alone is not delivery because it does not prove that a
receiver accepted the complete event.

## Decision

Version 0.16 adds one workspace Unix-socket delivery adapter. A canonical logical socket identifier
maps only to `.ansiblectl/events/sockets/IDENTIFIER.sock`. Ansiblectl never accepts an arbitrary
path and never creates, binds, replaces, removes, discovers, or supervises the receiver socket.

The adapter validates the private directory chain and socket metadata without following links,
connects with one fixed timeout, and verifies that the connected peer belongs to the effective user
through a supported kernel peer-credential mechanism. Platforms without reliable local peer
identity fail closed. The receiver cannot select a different user, group-sharing policy, abstract
namespace, socket type, or credential fallback.

One connection carries one event. The request is a four-byte unsigned big-endian content length
followed by the existing canonical event-envelope bytes. Delivery succeeds only after the exact
ASCII acknowledgement `ACK EVENT_ID\n` is received within a fixed bound, with EOF immediately
after it. Partial writes, partial reads, surplus bytes, wrong identifiers, timeout, peer change,
and protocol errors fail. The adapter performs no retry; the existing runner remains the sole owner
of claims, retry timing, exhaustion, and outbox acknowledgement.

Public results expose only stable socket delivery failure classes. Socket identifiers, paths, peer
credentials, payloads, protocol bytes, timing details, and exceptions never enter output, logs,
events, history, retry state, or object representations.

## Consequences

- Operator-controlled local receivers gain bounded push delivery without network configuration.
- Same-user peer verification and a fixed private root narrow, but do not eliminate, trust in other
  processes running as the workspace owner.
- Receivers must bind the canonical socket before delivery and implement the exact framed protocol.
- One connection per event makes acknowledgement boundaries simple and prevents stream
  resynchronization ambiguity.
- Socket path-length and peer-credential portability limitations become explicit fail-closed
  platform capabilities.

## Alternatives considered

Arbitrary Unix-socket paths were rejected because they escape workspace custody. A persistent
multi-event connection was rejected because retry after truncation makes stream position
ambiguous. Newline-delimited JSON was rejected because framing and acknowledgement remain
underspecified. Connect-only success was rejected because it can acknowledge undelivered bytes.
TCP loopback was rejected because port ownership and network policy require a different trust
model. Having ansiblectl create or supervise the receiver was rejected as a background-service and
inbound-lifecycle expansion.

## Compliance

TS-0034 defines selection, custody, peer verification, framing, acknowledgement, failure,
compatibility, lifecycle, redaction, and verification. Background services, inbound APIs, remote
commands, arbitrary paths, Windows named pipes, TCP, brokers, and a TUI remain out of scope.

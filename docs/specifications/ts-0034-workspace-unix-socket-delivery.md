# TS-0034: Workspace Unix Socket Delivery

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-04 |
| Related ADRs | [ADR-0051](../adr/0051-workspace-unix-socket-delivery.md), [ADR-0040](../adr/0040-durable-event-outbox.md), [ADR-0041](../adr/0041-local-event-delivery-runner.md), [ADR-0028](../adr/0028-workspace-lifecycle-and-isolation.md) |

## Purpose

Define bounded, fail-closed delivery of one durable event envelope to an operator-controlled local
Unix-domain socket while preserving the existing ordered at-least-once runner contract.

## Selection and namespace contract

A socket identifier MUST match `[a-z][a-z0-9._-]{0,127}` and is a logical identifier, never a path.
It maps only to `.ansiblectl/events/sockets/IDENTIFIER.sock` below the validated workspace root.
Empty, uppercase, Unicode, separator-containing, parent, absolute, URL, abstract-namespace,
null-byte, overlong, null, and non-string values are invalid.

The public command is
`event deliver CONSUMER --socket IDENTIFIER --max-events N`. `--socket`, `--archive`, and
`--endpoint` are mutually exclusive, and exactly one is required. The command does not register a
consumer, enumerate sockets, print the identifier, accept timeout or path overrides, or start a
background worker.

The platform-encoded final socket address MUST fit its complete kernel `sockaddr_un` limit with no
truncation, alternate encoding, working-directory dependency, or relative-path fallback. An
overlong workspace-derived address fails before socket creation or connection.

## Filesystem custody contract

The `.ansiblectl` and `events` ancestors retain their existing private workspace custody. The
`sockets` directory MUST be owned by the effective user, mode `0700`, a real directory, and reached
without following symlinks or traversing a replaced descriptor. Ansiblectl may create that
directory privately, but never creates or binds a receiver socket.

Immediately before connection, the selected target MUST be one filesystem Unix stream socket,
owned by the effective user, with mode `0600`. Symlinks, hard-link assumptions, regular files,
directories, devices, FIFOs, world/group permissions, wrong ownership, and non-filesystem or
abstract sockets fail closed. Metadata validation does not establish peer trust by itself.

After connection and before sending bytes, the adapter MUST obtain kernel-authenticated credentials
for the connected peer and prove its effective user identifier equals the ansiblectl effective user.
Linux `SO_PEERCRED` and macOS `getpeereid` are acceptable capability families. Missing, malformed,
ambiguous, changed, or unsupported peer credentials fail closed. Group membership, socket
ownership, process names, PIDs, environment, executable paths, and caller-supplied identity are not
substitutes. No privileged, root, group-shared, or cross-user override exists.

## Framing and acknowledgement contract

One adapter attempt opens exactly one `AF_UNIX` `SOCK_STREAM` connection and sends exactly one
request:

1. four bytes containing the canonical body length as an unsigned big-endian integer;
2. the envelope's existing canonical compact JSON bytes, with no newline or wrapper.

The body MUST be non-empty and at most 262,144 bytes. No consumer identifier, claim token, retry
count, hostname, workspace path, signature, timestamp, credential, content transform, compression,
or configurable header is added. The four-byte prefix counts bytes, not characters.

The adapter handles short writes but sends no byte more than once within the attempt. After the
complete request it shuts down its write side and reads a response bounded to exactly 31 bytes for
the canonical 26-character event identifier. The sole success response is the ASCII byte sequence
`ACK `, the exact request event identifier, and `\n`, followed immediately by EOF. Matching is
case-sensitive and byte-exact.

Empty, early EOF, late EOF, partial, oversized, surplus, non-ASCII, alternate whitespace, wrong
event identifier, negative acknowledgement, and response-before-complete-send conditions fail.
Connection, complete send, acknowledgement read, and close occur under one fixed 10-second
monotonic deadline. Configuration and CLI cannot widen, disable, or split that deadline.

## Outcome, lifecycle, and retry contract

Successful exact acknowledgement returns the existing delivered outcome. Every validation,
capability, address, ownership, permission, socket-type, connect, peer, deadline, send, receive,
shutdown, EOF, or protocol failure returns only `SOCKET_UNAVAILABLE`. The adapter does not retry,
sleep, reconnect, classify receiver details, or acknowledge the outbox internally.

The delivery runner remains the sole retry owner. Because the process may terminate or the
connection may fail after the receiver accepts an event but before outbox acknowledgement, delivery
remains at-least-once. Receivers MUST deduplicate by the stable event identifier. A later attempt
uses a new connection and resends the identical canonical envelope; it never resumes a partial
frame.

The operator owns receiver startup, shutdown, upgrade, stale-socket cleanup, capacity, and event
processing. Ansiblectl never creates, listens on, unlinks, replaces, repairs, probes in the
background, or supervises a socket or receiver process.

## Redaction and compatibility contract

Socket identifiers, absolute and relative paths, encoded addresses, peer user/group/process
credentials, protocol bytes, payloads, event identifiers in errors, byte counts, deadlines,
operating-system errors, and exception text MUST NOT appear in command output, logs, events,
history, retry records, SQLite, crash-safe state, or object representations. The receiver is the
selected event data surface and intentionally receives the canonical envelope.

Human, JSON, and YAML results reuse `DeliveryRunResult` schema version 1. Existing webhook and
archive adapters, consumer state, outbox schema and bytes, retry profiles, CLI commands, SDK
imports, event schemas, history, and exit codes retain exact behavior.

## Verification

- Identifier and address tests cover every invalid form and platform path-length boundary.
- Real-filesystem tests cover ancestor and target symlinks, types, ownership, permissions,
  replacement races, absent receivers, and stale sockets.
- Linux and macOS capability tests prove peer identity derives from the connected kernel socket and
  fails closed when unavailable or different.
- Fixed vectors prove the exact length prefix, canonical body, acknowledgement, write shutdown, and
  EOF contract at minimum and maximum body sizes.
- Fragmentation tests cover every request and response split; adversarial servers cover truncation,
  surplus bytes, wrong identifiers, early responses, stalls, disconnects, and deadline expiry.
- Subprocess tests terminate the sender before connect, during send, after send, after receiver
  acceptance, after acknowledgement, and before outbox acknowledgement.
- Raw durable-byte and public-surface tests prove identifiers, paths, peer metadata, payloads,
  protocol details, and exceptions remain absent outside the selected receiver.
- Hosted CI passes on Ubuntu and macOS with Python 3.12, 3.13, and 3.14 without external network
  access.

## Non-goals

- Creating, binding, discovering, unlinking, repairing, supervising, or installing receiver
  processes or sockets.
- Arbitrary or abstract socket paths, datagrams, sequenced packets, persistent connections, batch
  frames, multiplexing, streaming, negotiated protocols, or configurable timeouts.
- TCP, HTTP, RPC, brokers, syslog, named pipes, Windows support, plugins, commands, or shell piping.
- Cross-user or group-shared receivers, privilege changes, namespaces, containers, remote hosts, or
  network filesystems.
- Exactly-once delivery, receiver transactions, background workers, inbound APIs, hosted control
  planes, remote commands, or a TUI.

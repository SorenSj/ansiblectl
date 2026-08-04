# ADR-0043: Environment Secret Provider

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-04 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0011](0011-security-and-secret-handling.md), [ADR-0042](0042-outbound-https-webhook-delivery.md), [TS-0009](../specifications/ts-0009-secret-provider-contract.md), [TS-0026](../specifications/ts-0026-environment-secret-provider.md) |

## Context

Ansiblectl already models credentials as opaque `SecretReference` values and version 0.7 permits
optional bearer authentication for outbound HTTPS webhooks. The production composition root does
not provide a secret adapter, so authenticated delivery correctly fails closed. Operators need one
small non-interactive adapter that works with existing process supervisors and CI secret injection
without putting secret values in workspace files, arguments, command envelopes, or durable state.

Process environments are not a universal secret store. They inherit the operating system and
process supervisor's access controls and can be exposed by unsafe diagnostics or privileged process
inspection. This decision therefore defines a narrow retrieval boundary rather than claiming that
environment variables provide storage, rotation, revocation, or isolation.

## Decision

Version 0.8 introduces one production `env` secret provider. A reference has the form `env:NAME`,
where `NAME` is a canonical uppercase environment-variable name. The provider resolves exactly one
named value on demand, returns it through the existing reveal-once secret boundary, and does not
enumerate, cache, copy into diagnostics, or persist the process environment.

The CLI composes this provider only for the bounded foreground webhook-delivery command. It does
not accept secret values, environment-variable names, provider selection, or fallback values as
arguments. Workspace endpoint configuration continues to contain only a secret reference.

Missing, empty, malformed, undecodable, or control-character-bearing values fail closed before
network I/O with the existing public `AUTHENTICATION_UNAVAILABLE` delivery reason. Exceptions and
representations must not contain the reference key or value. Resolution has no fallback to another
provider and no implicit mapping from configuration secret aliases.

## Consequences

- Authenticated webhook delivery can use secrets injected by a local supervisor or CI system.
- No new dependency, network trust boundary, secret file format, or durable credential store is
  introduced.
- Operators remain responsible for environment injection, least-privilege process access, rotation,
  and removal after the foreground process exits.
- Keychain, vault, file, command, plugin, and cloud secret providers remain unavailable until their
  lifecycle and trust models are governed separately.

## Alternatives considered

CLI secret arguments were rejected because shell history and process listings can retain values.
Reading a workspace `.env` file was rejected because it would create a credential file format and
permission lifecycle. Executing a command to obtain a secret was rejected because it adds process,
path, output, timeout, and injection boundaries. Automatically selecting among multiple providers
was rejected because fallback can silently cross an operator's intended trust boundary.

## Compliance

TS-0026 defines reference syntax, lookup behavior, composition, error mapping, redaction, and
verification. Any provider that reads files, invokes commands, loads plugins, contacts a network
service, enumerates secrets, or persists material requires a separate decision before implementation.

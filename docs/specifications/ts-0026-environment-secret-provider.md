# TS-0026: Environment Secret Provider

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-04 |
| Related ADRs | [ADR-0043](../adr/0043-environment-secret-provider.md), [ADR-0011](../adr/0011-security-and-secret-handling.md), [ADR-0042](../adr/0042-outbound-https-webhook-delivery.md) |

## Purpose

Define a narrow production adapter that resolves an explicitly referenced process environment
variable through the existing secret boundary for bounded authenticated webhook delivery.

## Scope

This specification covers provider identity, canonical keys, lookup behavior, composition,
failure mapping, lifecycle, redaction, and compatibility. It does not define secret storage,
injection, rotation, revocation, or an environment-file format.

## Reference and lookup contract

The provider identifier is exactly `env`. Its key MUST match `[A-Z][A-Z0-9_]{0,127}`. Lowercase,
non-ASCII, whitespace, separators, shell expansion syntax, and longer keys are invalid. Validation
occurs before environment access.

One `resolve` call performs at most one exact-key lookup against an injected read-only environment
mapping. It MUST NOT enumerate keys, perform case folding, expand variables, parse quoting, trim
the value, search aliases, or fall back to another provider. The production composition supplies
the current process environment; tests supply an isolated mapping.

A present value is accepted only when it is non-empty Unicode text without C0/C1 control
characters, DEL, carriage return, or line feed. The adapter returns an existing `SecretValue`; it
does not expose public accessors, implement string conversion of the material, or retain an
additional cache.

## Failure and redaction contract

An unsupported provider, malformed key, absent key, empty value, invalid value, or lookup failure
raises the existing stable secret-resolution error without including the key, value, environment,
or underlying exception. Public webhook delivery maps every such failure to
`AUTHENTICATION_UNAVAILABLE` before DNS resolution or network I/O.

Secret keys and values MUST NOT appear in:

- object representations or exception text;
- human, JSON, or YAML output;
- structured logs or command envelopes;
- event payloads, delivery outcomes, retry state, or execution history;
- workspace configuration results or durable state.

Tests use conspicuous sentinel keys and values and inspect every public and durable surface for
their absence. Test failures and assertion messages must not interpolate material.

## Composition and lifecycle

The normal CLI composition root supplies the `env` provider only to
`event deliver CONSUMER --endpoint NAME --max-events N`. Resolution occurs after endpoint policy
validation and immediately before request construction. The revealed value is used only to build
the one request's authorization header, and application code drops the reference after the bounded
adapter call returns.

No CLI option accepts a secret value, key, provider, environment file, or fallback. Commands that
do not need authentication do not inspect the environment. The provider never mutates or clears
the parent process environment, since ownership remains with the process launcher.

## Compatibility and verification

- Fixed vectors cover every accepted and rejected key boundary.
- Mapping fakes prove exact single-key lookup without enumeration, fallback, trimming, or expansion.
- Missing, empty, invalid, and exceptional lookup paths produce one stable redacted failure.
- Webhook tests prove secret resolution precedes request construction but all resolution failures
  precede resolver, connector, and network activity.
- Human, JSON, YAML, logs, exceptions, state, and retry records contain neither sentinel keys nor
  sentinel values.
- Unauthenticated webhook delivery remains independent of environment contents.
- Existing secret protocols, v0.5 databases, v0.6 delivery behavior, v0.7 endpoint configuration,
  CLI commands, SDK imports, schemas, and exit codes remain compatible.
- The supported Python and operating-system CI matrix passes without external secret services or
  public network access.

## Non-goals

- `.env` files, workspace secret files, operating-system keychains, password managers, vaults, or
  cloud secret services.
- Command execution, shell expansion, templates, aliases, provider fallback, or secret discovery.
- Enumeration, mutation, rotation, revocation, caching, persistence, or background refresh.
- CLI secret input, interactive prompting, inbound APIs, background delivery, or remote control.

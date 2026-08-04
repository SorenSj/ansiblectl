# ADR-0047: Workspace File Secret Provider

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-04 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0011](0011-security-and-secret-handling.md), [ADR-0043](0043-environment-secret-provider.md), [ADR-0046](0046-signed-webhook-delivery.md), [TS-0009](../specifications/ts-0009-secret-provider-contract.md), [TS-0030](../specifications/ts-0030-workspace-file-secret-provider.md) |

## Context

The existing `env` provider permits bounded foreground webhook authentication and signing without
placing secret material in command arguments or durable application state. Process environments
are convenient for CI but are a poor fit for supervisors and container platforms that deliver
credentials as permission-restricted files. Operators currently have no supported way to use those
files and must copy their values into the process environment.

Reading an operator-selected path would introduce traversal, symlink, ownership, device, size, and
diagnostic-disclosure boundaries. Provider fallback would also make the selected custody boundary
ambiguous. A file provider therefore needs a fixed workspace-relative namespace and fail-closed
filesystem rules before it can join the existing secret-provider composition.

## Decision

Version 0.12 introduces one `file` provider. A reference has the form `file:NAME`, where `NAME` is a
bounded canonical identifier, not a path. It resolves exactly
`.ansiblectl/secrets/NAME` beneath the already validated workspace root. Neither configuration nor
the CLI can provide an alternate root, relative path, absolute path, extension, alias, or fallback.

Resolution opens the secrets directory and named entry without following symbolic links, then
validates the opened objects rather than trusting an earlier path check. The directory must be a
private directory owned by the current effective user. The entry must be a private, single-link,
same-owner regular file on the same device as the directory. Unsupported platforms or filesystems
fail closed. Material is read once with a strict byte bound, decoded as UTF-8, and accepted only
when non-empty and free of control characters. Contents are not trimmed, expanded, cached, logged,
or persisted.

The foreground webhook command composes an exact provider router containing `env` and `file`.
The provider named by the reference is called once; failures never fall back to the other provider.
Bearer and signing references may independently select either provider, including the same file,
but each resolution remains bounded and per attempt.

## Consequences

- Secrets provisioned as private files can authenticate and sign bounded webhook deliveries.
- The fixed workspace namespace is easy to exclude from source control and audit, but operators
  remain responsible for secure provisioning, rotation, backup exclusion, and deletion.
- Strict ownership, permission, link, type, device, encoding, and size checks reject some otherwise
  readable files rather than weakening custody silently.
- The provider remains POSIX-oriented until another platform can demonstrate equivalent
  descriptor-relative, no-follow validation in dedicated CI.

## Alternatives considered

Arbitrary paths in secret references were rejected because they expose path material and permit
workspace escape. A configurable root was rejected because it adds precedence and lifecycle rules
without a current requirement. Automatic `env` fallback was rejected because it can silently cross
the selected trust boundary. Trimming a terminal newline was rejected because it changes secret
bytes implicitly. Watching files or caching values was rejected because bounded foreground
resolution already observes rotation on the next attempt.

## Compliance

TS-0030 defines namespace syntax, descriptor-relative validation, material bounds, composition,
failure mapping, redaction, compatibility, and adversarial verification. Command, keychain, vault,
plugin, and network secret providers still require separate decisions.

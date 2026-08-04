# TS-0030: Workspace File Secret Provider

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-04 |
| Related ADRs | [ADR-0047](../adr/0047-workspace-file-secret-provider.md), [ADR-0011](../adr/0011-security-and-secret-handling.md), [ADR-0043](../adr/0043-environment-secret-provider.md) |

## Purpose

Define a fail-closed adapter that resolves an explicitly named private workspace file through the
existing secret boundary for bounded webhook authentication and signing.

## Scope

This specification covers provider identity, canonical names, fixed placement, filesystem
validation, material parsing, composition, failure mapping, lifecycle, redaction, and
compatibility. It does not define secret creation, synchronization, backup, rotation, or deletion.

## Reference and namespace contract

The provider identifier is exactly `file`. Its key MUST match
`[A-Z][A-Z0-9_]{0,63}`. Lowercase, non-ASCII, whitespace, dots, slashes, separators, percent
encoding, shell syntax, and longer keys are invalid. Validation occurs before filesystem access.

The only candidate is `.ansiblectl/secrets/NAME` beneath the validated workspace root. The
provider MUST NOT accept a path, alternate root, extension, environment override, alias, search,
or fallback. Public results and errors identify neither the candidate nor its components.

## Filesystem custody contract

One resolution performs descriptor-relative, no-follow access and validates the opened objects.
Before material is returned, all of the following MUST hold:

1. `.ansiblectl` and `.ansiblectl/secrets` are real directories, not symbolic links, owned by the
   effective user, and grant no group or other permission bits.
2. `NAME` is opened without following symbolic links and is a regular file owned by the effective
   user, with link count exactly one and no group or other permission bits.
3. The file and directory are on the same device, and their identity remains the identity checked
   through the open descriptors.
4. The implementation can provide the required descriptor-relative and no-follow guarantees on
   the current platform and filesystem.

Missing objects, unsafe ancestors, ownership mismatch, excess permissions, links, non-regular
objects, device mismatch, races, or unsupported capabilities produce the same stable resolution
failure. Validation never repairs permissions or mutates filesystem state.

## Material contract

The provider reads at most 8,193 bytes from the validated descriptor and rejects content larger
than 8,192 bytes. Accepted content is strict UTF-8, non-empty, and contains no C0 or C1 control
characters or DEL. No byte is stripped or normalized; in particular a terminal carriage return or
line feed is invalid. The adapter returns the existing reveal-once material object and retains no
additional copy or cache after the call.

## Composition, routing, and lifecycle

The normal CLI composition root supplies an exact provider router containing `env` and `file` only
to the bounded foreground webhook-delivery command. Routing is an exact match on the reference's
provider. An unknown provider or any selected-provider failure terminates resolution without
calling another provider.

Endpoint validation completes before secret access. Every required bearer and signing reference
is resolved before DNS, socket, TLS, or HTTP activity. Each reference is resolved at most once per
delivery attempt. A subsequent attempt reopens and revalidates the selected file so atomic
operator-managed replacement can rotate material between attempts. The provider does not watch,
lock, rewrite, remove, cache, or persist the file.

## Failure and redaction contract

Every malformed name, unavailable capability, unsafe object, read failure, invalid material, or
unsupported provider raises the existing stable secret-resolution error without including a key,
path, file metadata, content, operating-system error, or underlying exception. Authentication use
maps this to `AUTHENTICATION_UNAVAILABLE`; signing use maps it to `SIGNING_UNAVAILABLE`.

Keys, paths, material, metadata, and exception details MUST NOT appear in object representations,
human/JSON/YAML output, structured logs, command envelopes, events, delivery outcomes, retry state,
history, configuration results, SQLite state, or other durable files. Adversarial tests inspect raw
durable bytes as well as decoded public surfaces.

## Compatibility and verification

- Boundary vectors cover every accepted and rejected provider key.
- Descriptor-level tests cover absent objects, symlinks at every controlled component, owner and
  mode mismatch, multiple links, directories/devices/FIFOs/sockets, oversize content, and
  replacement races without blocking on special files.
- Material vectors cover UTF-8 boundaries, emptiness, controls, terminal newlines, and the exact
  8,192-byte limit.
- Router tests prove exact one-provider dispatch, no fallback, bounded calls, and stable failures.
- Webhook tests prove all required material is available before DNS and that bearer, signing,
  network-policy, and exclusive-trust combinations retain their existing behavior.
- Existing `env` references, endpoint schemas 1 through 4, v0.5 databases, CLI/SDK/event/history
  contracts, retry semantics, and output schemas remain compatible.
- Hosted CI passes on Ubuntu and macOS with Python 3.12, 3.13, and 3.14 without public network or
  external secret services.

## Non-goals

- Arbitrary or absolute paths, configurable roots, home expansion, extensions, recursive lookup,
  aliases, enumeration, or provider fallback.
- Automatic creation, permission repair, locking, synchronization, backup, rotation, revocation,
  deletion, watching, or caching.
- Newline trimming, decoding fallback, binary material, templating, interpolation, or expansion.
- Keychains, password managers, vaults, cloud services, plugins, command execution, or remote
  retrieval.
- CLI secret input, prompts, background delivery, inbound APIs, remote control, or a TUI.

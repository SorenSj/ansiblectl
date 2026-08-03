# TS-0013: Plugin Permission Enforcement

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-03 |
| Related ADRs | [ADR index](../adr/README.md) |

## Purpose

Defines permission declaration, grants, denial behaviour, and capability-scoped plugin contexts.

## Scope

This specification defines the initial public and internal contract for this capability. Implementation details that do not alter the stated contract remain flexible.

## Functional requirements

1. Every privileged capability MUST map to a named permission.
2. A plugin MUST declare requested permissions in its manifest.
3. The runtime MUST deny undeclared or ungranted capabilities before plugin code can use them.
4. Permission decisions MUST be observable through safe diagnostics.
5. The default policy MUST be least privilege.

## Interfaces and data

The permission service resolves a manifest request and policy into a granted capability set used to build the plugin context.

The initial policy is default-deny. Privileged capabilities map one-to-one to
named permissions (`network`, `secrets`, and `filesystem_write`); an unknown or
ungranted request fails with a safe diagnostic before privileged work starts.

## Verification

- An ungranted secret capability is unavailable in plugin context.
- A denied permission produces a clear diagnostic without executing privileged work.
- Tests cover default-deny and explicit-grant behaviour.

## Non-goals

This specification does not introduce unrelated delivery mechanisms, hosted services, or public APIs beyond the contract described above.

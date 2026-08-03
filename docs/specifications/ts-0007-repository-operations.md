# TS-0007: Repository Operations

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-03 |
| Related ADRs | [ADR index](../adr/README.md) |

## Purpose

Defines repository discovery, clone, fetch, revision selection, synchronisation, and safe working-tree handling.

## Scope

This specification defines the initial public and internal contract for this capability. Implementation details that do not alter the stated contract remain flexible.

## Functional requirements

1. Repository operations MUST be scoped to a validated workspace path.
2. A requested revision MUST be explicit or resolved according to documented policy.
3. Mutating operations MUST report the repository and revision target before acting.
4. Credentials MUST be supplied through secret references or environment policy, never command arguments or logs.
5. Conflicts, dirty worktrees, and authentication failures MUST be classified and actionable.

## Interfaces and data

The repository port accepts a RepositoryRequest and returns typed state and operation results; Git is an adapter, not a public domain dependency.

## Verification

- A fake repository port validates application orchestration.
- A dirty worktree failure does not overwrite user changes.
- Credentials are absent from rendered command diagnostics.

## Non-goals

This specification does not introduce unrelated delivery mechanisms, hosted services, or public APIs beyond the contract described above.


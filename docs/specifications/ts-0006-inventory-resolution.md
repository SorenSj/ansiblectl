# TS-0006: Inventory Resolution

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-03 |
| Related ADRs | [ADR index](../adr/README.md) |

## Purpose

Defines inventory source loading, validation, merge policy, provenance, and canonical execution representation.

## Scope

This specification defines the initial public and internal contract for this capability. Implementation details that do not alter the stated contract remain flexible.

## Functional requirements

1. Inventory sources MUST implement a provider contract.
2. Resolved hosts and groups MUST be validated before execution.
3. Conflicting values MUST follow a documented precedence policy or produce an error.
4. The resolved inventory MUST retain non-secret provenance where practical.
5. The execution adapter MUST receive a canonical generated representation rather than raw provider internals.

## Interfaces and data

The inventory service returns a typed ResolvedInventory with hosts, groups, variables, diagnostics, and provenance metadata.

The initial merge policy is low-to-high provider precedence: a later host with
the same name replaces the earlier definition and records a diagnostic naming
both sources. Groups may reference only resolved hosts. The generated adapter
representation has sorted `hosts` with address and variables, plus sorted
`groups` with host-name lists; providers themselves are never passed to an
execution adapter.

## Verification

- Two providers with a declared precedence resolve predictably.
- An invalid host definition fails before execution.
- A fake provider can be used in application tests.

## Non-goals

This specification does not introduce unrelated delivery mechanisms, hosted services, or public APIs beyond the contract described above.

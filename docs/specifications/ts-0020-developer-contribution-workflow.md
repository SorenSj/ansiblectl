# TS-0020: Developer Contribution Workflow

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-03 |
| Related ADRs | [ADR index](../adr/README.md) |

## Purpose

Defines issue-to-change traceability, review expectations, local checks, and definition of done for contributors.

## Scope

This specification defines the initial public and internal contract for this capability. Implementation details that do not alter the stated contract remain flexible.

## Functional requirements

1. Material changes MUST reference a requirement, issue, ADR, or TS as appropriate.
2. Contributors MUST run documented local quality checks before review.
3. Reviews MUST verify applicable tests, documentation, public-contract impact, and migration guidance.
4. A completed change MUST satisfy the Engineering Principles definition of done.
5. Exceptions MUST record owner, scope, rationale, and expiry or removal plan.

## Interfaces and data

The contribution guide and pull-request template reference the same required checks and normative document hierarchy.

The repository pull-request template captures traceability, verification, and
the required owner, scope, rationale, and expiry/removal plan for any temporary
exception.

## Verification

- A documentation-only change is validated through the same link and metadata checks.
- A public-contract change review includes compatibility evidence.
- An exception example includes all required fields.

## Non-goals

This specification does not introduce unrelated delivery mechanisms, hosted services, or public APIs beyond the contract described above.

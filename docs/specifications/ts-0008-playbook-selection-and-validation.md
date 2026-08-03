# TS-0008: Playbook Selection and Validation

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-03 |
| Related ADRs | [ADR index](../adr/README.md) |

## Purpose

Defines how a playbook is identified, located, and validated before it is executed.

## Scope

This specification defines the initial public and internal contract for this capability. Implementation details that do not alter the stated contract remain flexible.

## Functional requirements

1. A playbook identifier MUST resolve within the configured project or repository boundary.
2. Resolution MUST reject paths that escape the declared content root.
3. The system MUST verify existence and supported file type before execution.
4. Additional syntax or lint validation MAY be requested explicitly and MUST report tool provenance.
5. Selected playbook and revision MUST be recorded in the execution request.

## Interfaces and data

The selection service returns a typed PlaybookReference containing canonical path, repository revision, and validation findings.

The initial selector accepts `.yml` and `.yaml` files only. Relative identifiers
are resolved against the declared content root, while absolute identifiers must
still be contained by it. The resulting reference stores the canonical path and
explicit repository revision; optional syntax/lint findings may be added later.

## Verification

- A relative path resolves reproducibly within a workspace.
- Traversal outside a content root is rejected.
- The execution request contains the canonical selected playbook.

## Non-goals

This specification does not introduce unrelated delivery mechanisms, hosted services, or public APIs beyond the contract described above.

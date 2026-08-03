# TS-0018: Architecture and Documentation Validation

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-03 |
| Related ADRs | [ADR index](../adr/README.md) |

## Purpose

Defines automated checks that ensure normative documentation and package boundaries remain consistent.

## Scope

This specification defines the initial public and internal contract for this capability. Implementation details that do not alter the stated contract remain flexible.

## Functional requirements

1. CI MUST validate Markdown links and required metadata for normative documents.
2. The ADR and TS indexes MUST reference every numbered artifact exactly once.
3. Import-boundary checks MUST enforce the dependency rules in the Architecture Handbook.
4. Validation failures MUST name the artifact, rule, and corrective action.
5. Validation configuration MUST itself be version-controlled.

## Interfaces and data

The validation command returns structured findings suitable for CI and a concise human summary.

## Verification

- A broken relative link fails validation.
- A forbidden layer import fails validation.
- An orphaned numbered ADR or TS is detected.

## Non-goals

This specification does not introduce unrelated delivery mechanisms, hosted services, or public APIs beyond the contract described above.


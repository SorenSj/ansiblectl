# TS-0003: Configuration Resolution

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-03 |
| Related ADRs | [ADR index](../adr/README.md) |

## Purpose

Defines typed configuration sources, precedence, interpolation limits, diagnostics, and effective configuration output.

## Scope

This specification defines the initial public and internal contract for this capability. Implementation details that do not alter the stated contract remain flexible.

## Functional requirements

1. Configuration MUST be loaded in the precedence order declared by ADR-0008.
2. Each source MUST be associated with a path or origin for diagnostics.
3. Values MUST be validated into typed models before use.
4. Environment variables MAY override only documented fields.
5. Secret values MUST be represented by references and MUST NOT appear in effective-configuration output.
6. Invalid configuration MUST report the field, source, and safe corrective action.

## Interfaces and data

The configuration service receives source locations and command overrides and returns a validated model plus non-secret provenance metadata.

The initial YAML schema contains `schema_version: 1`, optional `project_name`,
optional `log_level` (`debug`, `info`, `warning`, or `error`), and optional
`secrets` mappings whose values are `provider:key` references. The documented
files are `~/.config/ansiblectl/config.yaml`, `.ansiblectl/config.yaml`, and
`ansiblectl.yaml` within the selected workspace. `ANSIBLECTL_LOG_LEVEL` is the
only environment override in this initial contract.

## Verification

- A higher-precedence valid value overrides a lower-precedence value.
- An unknown or invalid field fails before an operation runs.
- Effective configuration output redacts secret references and values as specified.

## Non-goals

This specification does not introduce unrelated delivery mechanisms, hosted services, or public APIs beyond the contract described above.

# TS-0010: Provider Manifest and Discovery

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-03 |
| Related ADRs | [ADR index](../adr/README.md) |

## Purpose

Defines the manifest contract used to discover, validate, and register provider plugins.

## Scope

This specification defines the initial public and internal contract for this capability. Implementation details that do not alter the stated contract remain flexible.

## Functional requirements

1. A manifest MUST declare identity, version, SDK compatibility, capabilities, configuration schema reference, and requested permissions.
2. Discovery MUST validate manifest shape before importing plugin code.
3. Duplicate provider identities or incompatible versions MUST fail deterministically.
4. A failed optional provider MUST not corrupt the core registry.
5. Manifest diagnostics MUST identify the source and failed field without exposing secrets.

## Interfaces and data

The runtime accepts manifests from configured locations and returns validated ProviderDescriptor records before plugin initialisation.

## Verification

- Malformed manifests fail before code import.
- An incompatible SDK range prevents provider registration.
- Duplicate identity handling is covered by a registry test.

## Non-goals

This specification does not introduce unrelated delivery mechanisms, hosted services, or public APIs beyond the contract described above.


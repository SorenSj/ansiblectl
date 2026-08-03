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

The initial manifest requires `identity`, `version`, `sdk_compatibility`,
`capabilities`, `configuration_schema`, and `permissions`. SDK compatibility is
currently exact (`0.1`). All manifests are parsed before descriptors are
registered, so a malformed or duplicate descriptor leaves no partial registry.
Configured filesystem locations use safe YAML parsing; discovery has no plugin
code-import step.

`plugin discover --directory <path>` scans one workspace-contained directory
(default `plugins`) for direct `.yml` and `.yaml` children in deterministic name
order. Nested content and non-YAML files are ignored; directory and manifest
symlinks are rejected. All selected manifests still validate as one registry,
so malformed or duplicate descriptors produce no partial result.

## Verification

- Malformed manifests fail before code import.
- An incompatible SDK range prevents provider registration.
- Duplicate identity handling is covered by a registry test.
- Directory discovery is deterministic and never follows manifest symlinks.

## Non-goals

This specification does not introduce unrelated delivery mechanisms, hosted services, or public APIs beyond the contract described above.

# TS-0012: Plugin SDK Contracts

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-03 |
| Related ADRs | [ADR index](../adr/README.md) |

## Purpose

Defines the stable Python surface available to first-party and third-party plugin authors.

## Scope

This specification defines the initial public and internal contract for this capability. Implementation details that do not alter the stated contract remain flexible.

## Functional requirements

1. The SDK MUST expose only documented public modules, types, decorators, and context capabilities.
2. Public symbols MUST be typed and documented.
3. The SDK MUST avoid exposing concrete core adapters or mutable global registries.
4. Compatibility MUST be checked against the manifest-declared SDK range.
5. SDK test utilities MUST provide mock context and fake capability implementations.

## Interfaces and data

The public namespace is `ansiblectl.sdk`; all other `ansiblectl` imports are internal and unsupported for plugins.

## Verification

- A plugin importing only the SDK passes compatibility tests.
- An SDK API change is detected by public-surface tests.
- Mock context supports a plugin unit test without core startup.

## Non-goals

This specification does not introduce unrelated delivery mechanisms, hosted services, or public APIs beyond the contract described above.


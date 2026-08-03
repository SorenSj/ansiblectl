# ADR-0025: Plugin SDK Compatibility and Distribution

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

Plugins require a stable, independently understandable contract and installation path.

## Decision

The SDK is versioned as a public contract and declares its supported core compatibility range. Plugins declare their compatible SDK range in a manifest and are validated before loading. Initial distribution uses standard Python packaging; custom archives or signing require a future ADR.

## Consequences

Plugin compatibility can be checked before execution and distribution uses familiar tools. The SDK must avoid leaking internal types and needs compatibility tests.

## Alternatives considered

Loading arbitrary Python modules without manifest or compatibility validation was rejected because failures would be late and unsafe.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


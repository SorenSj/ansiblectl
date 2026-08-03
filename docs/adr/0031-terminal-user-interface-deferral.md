# ADR-0031: Terminal User Interface Deferral

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

A rich terminal interface could improve exploration but must not destabilise the primary command contract.

## Decision

The primary interface remains composable commands with human and machine-readable output. A TUI is deferred until command workflows and domain use cases are validated. A future TUI must be a delivery adapter over application services, not a second business-logic layer.

## Consequences

The project concentrates on reliable automation first. Interactive workflows remain a future opportunity rather than a core commitment.

## Alternatives considered

Making a TUI the initial interface was rejected because it would slow scripting support and duplicate CLI concerns.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


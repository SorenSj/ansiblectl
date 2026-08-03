# ADR-0006: Typed Configuration Model

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

Operators need configuration that is predictable, validated, and safe to evolve.

## Decision

Configuration is represented by typed, versioned models at every public boundary. Parsing converts source data into validated models before use; application and domain code do not consume unstructured configuration dictionaries.

## Consequences

Invalid input fails early with useful diagnostics and refactoring becomes safer. Models introduce maintenance work and their public fields require compatibility discipline.

## Alternatives considered

Ad hoc dictionary access was rejected because it defers errors and obscures the supported configuration contract.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


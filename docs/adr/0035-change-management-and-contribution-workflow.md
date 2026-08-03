# ADR-0035: Change Management and Contribution Workflow

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

The project needs a consistent path from idea to safe release as contributors and documentation grow.

## Decision

Material changes follow the lifecycle defined by Engineering Principles: requirement, design or ADR when needed, Technical Specification when needed, implementation, automated verification, documentation, review, and release. Changes are small, traceable, and reviewed through Git-based pull requests.

## Consequences

Decision history, code, and documentation remain connected and reviewable. Maintainers must enforce scope discipline and keep contribution guidance current.

## Alternatives considered

Direct changes without review or traceability were rejected because they make governance and regression prevention ineffective.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


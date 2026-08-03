# ADR-0021: Versioning and Release Strategy

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

Users and plugin authors need clear expectations about stability and upgrades.

## Decision

Ansiblectl follows Semantic Versioning. During 0.x releases, public contracts are marked experimental unless explicitly declared stable. A 1.0 release requires documented stable CLI and SDK contracts, release notes, and supported-runtime policy.

## Consequences

Compatibility expectations become explicit and release notes become meaningful. Release work requires disciplined change classification.

## Alternatives considered

Calendar versioning was rejected because it does not communicate compatibility impact.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


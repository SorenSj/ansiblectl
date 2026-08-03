# ADR-0024: Continuous Integration Quality Gates

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

Required quality checks must be repeatable before changes are merged.

## Decision

Every change runs the project’s configured formatter, linter, type checker, unit tests, relevant integration tests, documentation validation, and architecture-boundary checks. Required checks cannot be bypassed except through a documented maintainer exception.

## Consequences

Quality rules are consistently enforced and regressions are caught early. CI configuration and test speed must be actively maintained.

## Alternatives considered

Optional local checks alone were rejected because results vary by contributor environment.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


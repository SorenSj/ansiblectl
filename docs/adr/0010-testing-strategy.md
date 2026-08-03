# ADR-0010: Testing Strategy

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

The project needs confidence in core policy, integrations, public contracts, and regressions.

## Decision

Tests follow a layered strategy: unit tests for domain rules, use-case tests with fakes, adapter contract tests, CLI tests, integration tests, and SDK/plugin compatibility tests. Every defect receives a regression test unless infeasible and documented.

## Consequences

Failures are localised and public behaviour gains protection. Test fixtures and CI time become a maintained product concern.

## Alternatives considered

An integration-test-only strategy was rejected because it is slow, fragile, and cannot isolate domain policy.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


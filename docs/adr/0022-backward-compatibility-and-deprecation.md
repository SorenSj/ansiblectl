# ADR-0022: Backward Compatibility and Deprecation

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

Public contracts must evolve without surprising operators or plugin authors.

## Decision

Documented public CLI, configuration, machine output, and SDK surfaces remain compatible within a major version. Deprecations provide a supported alternative, warning where appropriate, and a stated removal version or date. Breaking changes require a major release and migration guidance.

## Consequences

Users can plan upgrades and maintainers have a consistent removal process. Compatibility tests and temporary adapters increase maintenance cost.

## Alternatives considered

Silent removal or behavioural change in a minor release was rejected because it erodes trust.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


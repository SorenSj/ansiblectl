# ADR-0028: Workspace Lifecycle and Isolation

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

Commands need a safe, repeatable local boundary for files, configuration, repositories, and state.

## Decision

A workspace is explicitly selected or initialised before project-scoped operations. Workspace discovery, layout, lifecycle, and mutation rules are part of the public CLI contract. Operations must not write outside their declared workspace except for documented user-scoped cache or configuration locations.

## Consequences

Targets and side effects are clear, and multiple projects can coexist safely. Workspace initialisation and migration need dedicated specifications.

## Alternatives considered

Implicitly treating the current directory as an unrestricted project root was rejected because it makes destructive operations ambiguous.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


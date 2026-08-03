# ADR-0004: Dependency Injection and Composition Root

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

Use cases must receive explicit dependencies while keeping construction at the application edge.

## Decision

The CLI is the composition root. It constructs concrete adapters and injects them into application services. Global mutable service registries, hidden singletons, and ambient dependencies are prohibited. Tests use explicit fakes.

## Consequences

This makes dependencies visible and unit tests independent of the filesystem, network, and Ansible. It adds modest construction code and requires interfaces to be designed deliberately.

## Alternatives considered

A global service locator was rejected because it hides dependencies and weakens test isolation.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


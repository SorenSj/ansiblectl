# ADR-0018: Event Publication Model

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

Plugins and observability integrations need decoupled notification of meaningful lifecycle events.

## Decision

The system may publish typed, documented domain-relevant events after committed use-case transitions. Events are additive notifications, not a hidden command bus; handlers must not be required for core correctness and event payloads contain no secrets.

## Consequences

Optional integrations can observe operations without direct coupling. Event versions, ordering, and delivery guarantees must be specified before a public event API is stable.

## Alternatives considered

Unstructured in-process callbacks were rejected because they obscure ownership and create brittle execution paths.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


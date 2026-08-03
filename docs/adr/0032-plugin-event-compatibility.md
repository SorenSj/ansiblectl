# ADR-0032: Plugin Event Compatibility

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

Plugins may observe lifecycle events, so event changes can become public compatibility commitments.

## Decision

Only events documented in the SDK are public. Public events have stable names, typed payload schemas, and compatibility rules aligned with the SDK major version. Delivery is in-process and best-effort unless a future specification explicitly defines persistence, ordering, or retries.

## Consequences

Plugin authors can rely on a small, clear event surface. The project avoids accidentally promising delivery guarantees it cannot meet.

## Alternatives considered

Publishing every internal event was rejected because it would freeze implementation details and create an unbounded contract.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


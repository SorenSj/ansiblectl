# ADR-0005: Plugin Architecture

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

Integrations must evolve without coupling their release cadence to the core.

## Decision

Ansiblectl uses a plugin-first extension model. Plugins contribute only through the public SDK, a validated manifest, declared capabilities, and explicit lifecycle hooks. The core retains essential safety, workspace, execution, and contract responsibilities.

## Consequences

The project gains an extensible ecosystem and a smaller core. Plugin discovery, compatibility, and failure isolation must be implemented and tested.

## Alternatives considered

Direct imports of integration modules into core commands were rejected because they make every integration a core compatibility commitment.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


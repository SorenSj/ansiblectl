# ADR-0014: Provider Architecture

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

Repositories, inventory sources, secret stores, and future integrations vary by environment.

## Decision

Provider capabilities are represented by domain-owned ports and implemented by infrastructure or plugins. Providers declare capabilities, configuration schema, permissions, and compatibility through the SDK; application services depend on ports, not provider identities.

## Consequences

External systems remain replaceable and testable. Provider contracts need careful versioning and capability discovery.

## Alternatives considered

Embedding provider-specific logic in application services was rejected because it couples the core to vendor behaviour.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


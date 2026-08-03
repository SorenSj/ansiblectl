# ADR-0019: Local State, Cache, and Persistence

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

The CLI needs small amounts of state without assuming a central service or database.

## Decision

The product is local-first. Persistent state and caches are owned by explicit ports, scoped to a workspace or user location, versioned where necessary, and safe to discard when documented as cache. Core domain objects do not depend on a storage technology.

## Consequences

Initial operation stays simple and offline-friendly. State migrations, locking, and retention require specification before persistent features are added.

## Alternatives considered

A mandatory central database was rejected because it conflicts with local-first operation and adds unsupported operational burden.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


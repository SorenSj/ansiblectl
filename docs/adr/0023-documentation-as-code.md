# ADR-0023: Documentation as Code

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

Architecture, behaviour, and operational guidance must remain aligned with implementation.

## Decision

Normative documentation lives in the repository, is reviewed with code, uses stable identifiers, and is validated in CI. ADRs are immutable history; technical specifications and handbook versions are maintained as versioned artefacts.

## Consequences

Documentation has traceability and shared ownership. Documentation reviews and link validation become required engineering work.

## Alternatives considered

External wiki-only governance was rejected because it can drift from reviewed source changes.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


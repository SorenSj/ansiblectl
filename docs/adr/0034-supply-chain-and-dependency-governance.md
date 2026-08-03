# ADR-0034: Supply Chain and Dependency Governance

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

A Python CLI and plugin ecosystem depend on third-party packages and may execute extensions.

## Decision

Dependencies must be declared, version constrained, and reviewed. The build and release process must produce traceable artifacts and run vulnerability and license checks appropriate to the project. Plugin provenance, signing, and registry trust policy are deferred to a dedicated future ADR.

## Consequences

The project gains a baseline for reproducible, auditable releases. Dependency updates and security review require continuous maintenance.

## Alternatives considered

Unpinned, ad hoc runtime installation was rejected because it undermines reproducibility and security review.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


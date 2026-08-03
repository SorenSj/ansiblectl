# ADR-0017: Ansible Execution Architecture

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

Ansiblectl must run Ansible safely without duplicating its semantics.

## Decision

Ansible execution is an infrastructure adapter behind an execution port. An application use case prepares validated inventory, configuration, repository state, arguments, environment policy, and working directory; the adapter returns a structured execution result.

## Consequences

Execution is testable and command construction is controlled. Exact CLI argument mapping and output capture require a Technical Specification.

## Alternatives considered

Embedding Ansible-specific state in domain entities was rejected because it couples product rules to one execution technology.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


# ADR-0027: Public API Classification

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

Not every module can carry a long-term compatibility obligation.

## Decision

Interfaces are classified as internal, protected, or public. Only documented public CLI, SDK, configuration, and output contracts receive compatibility guarantees. Protected interfaces are maintainer-facing and may change with notice; internal modules may change without notice.

## Consequences

Maintainers preserve freedom to refactor while users know what is safe to depend on. Documentation must mark public boundaries clearly.

## Alternatives considered

Treating every importable symbol as public was rejected because it would freeze implementation details prematurely.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


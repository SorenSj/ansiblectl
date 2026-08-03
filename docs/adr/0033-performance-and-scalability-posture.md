# ADR-0033: Performance and Scalability Posture

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

Automation workloads range from small local projects to larger inventories, but performance work needs evidence.

## Decision

Correctness, safety, and observability take precedence over speculative optimisation. The project measures representative operations before optimisation, sets explicit budgets in specifications where needed, and keeps I/O, caching, and concurrency behind ports. Parallelism must preserve deterministic user-visible results.

## Consequences

The architecture can improve performance without leaking concurrency into domain rules. Benchmarking and profiling become part of performance work.

## Alternatives considered

Premature global concurrency and caching were rejected because they add nondeterminism and invalidation risks without measured benefit.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


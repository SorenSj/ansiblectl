# ADR-0020: Machine-Readable Output Contract

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

CI and integrations need results that are stable without parsing terminal prose.

## Decision

Commands that support automation expose an explicit machine-readable output mode with a documented schema and version. Human output remains independent. Output schemas are public contracts and incompatible changes follow the compatibility policy.

## Consequences

Automation becomes reliable and human UX can evolve separately. Schemas, examples, and contract tests must be maintained.

## Alternatives considered

Screen scraping human-formatted tables was rejected because formatting changes would silently break callers.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


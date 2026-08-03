# ADR-0012: Logging and Observability

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

Operators and maintainers need to understand execution without exposing sensitive data.

## Decision

Core operations emit structured logs with stable event names, severity, execution correlation, and redaction. Human-oriented diagnostics are rendered by the CLI; metrics and tracing remain optional integrations until a concrete operational need is approved.

## Consequences

Supportability improves while local-first operation stays lightweight. Log schemas and redaction rules become contracts that require review.

## Alternatives considered

Unstructured print-based diagnostics were rejected because they cannot reliably support automation or incident analysis.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


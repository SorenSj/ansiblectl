# ADR-0013: CLI User Experience and Exit Codes

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

The CLI is the primary interface for people and CI.

## Decision

Commands MUST be discoverable through consistent help, predictable argument conventions, actionable errors, and documented exit codes. Human-readable output is the default; stable machine-readable output is opt-in and versioned. Destructive actions require explicit intent.

## Consequences

Interactive and automated callers receive reliable behaviour. CLI changes require compatibility and output-contract tests.

## Alternatives considered

A separate CI-only command surface was rejected because it duplicates use cases and creates inconsistent behaviour.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


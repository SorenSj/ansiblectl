# ADR-0009: Error Handling Strategy

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

Automation failures must be safe for people and reliable for callers.

## Decision

Domain and application code uses typed, meaningful failures. Infrastructure maps external failures into those types; the CLI maps them to documented messages and exit codes. Unexpected failures are safely reported without secrets or stack traces by default.

## Consequences

Errors are testable and scriptable, with clearer remediation. Error taxonomy and mappings require ongoing maintenance.

## Alternatives considered

Returning sentinel values or printing errors deep in the stack was rejected because it loses context and mixes responsibilities.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


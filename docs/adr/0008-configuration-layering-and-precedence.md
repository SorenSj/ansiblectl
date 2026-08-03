# ADR-0008: Configuration Layering and Precedence

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

Configuration comes from defaults, project files, environment-aware sources, and explicit invocation options.

## Decision

Configuration uses an explicit, documented precedence order: built-in defaults, user configuration, workspace configuration, project configuration, environment variables, and explicit CLI arguments. Later sources override earlier sources only where the model permits it.

## Consequences

Operators can predict effective configuration and CI remains reproducible. Each layer needs source-aware diagnostics and tests.

## Alternatives considered

Implicit discovery and undocumented environment overrides were rejected because they create hidden state.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


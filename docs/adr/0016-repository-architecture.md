# ADR-0016: Repository Architecture

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

Automation content must be discoverable, reproducible, and safe to synchronise.

## Decision

Repository operations are performed through a repository port with explicit workspace paths, revisions, credentials, and results. Git is the initial adapter; callers operate on repository contracts rather than shell commands.

## Consequences

Git behaviour can be tested and future providers remain possible. Repository lifecycle, authentication, and conflict policy need a Technical Specification.

## Alternatives considered

Calling Git directly from command handlers was rejected because it mixes orchestration, process execution, and user rendering.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


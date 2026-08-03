# ADR-0029: Policy Evaluation Architecture

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

Teams may need guardrails for configuration and execution without hard-coding organisation rules into the core.

## Decision

Policy evaluation is an optional, explicit application capability. Policies consume validated models and produce structured findings before a governed operation proceeds. The initial core defines policy ports and result contracts; policy languages and bundled rules require a Technical Specification.

## Consequences

Governance can be added without contaminating domain rules with local organisational choices. Policy ordering and enforcement modes require careful design.

## Alternatives considered

Embedding organisation-specific validation directly in command handlers was rejected because it cannot be reused or configured consistently.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


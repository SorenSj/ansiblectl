# ADR-0026: Plugin Permission Model

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

Extensions may access repositories, execution, secrets, network services, and output.

## Decision

Plugins request named capabilities in their manifest. The runtime validates and grants only approved capabilities through the SDK context. The initial permission policy is local and explicit; unattended or enterprise policy enforcement requires a future specification.

## Consequences

Plugin authority is visible and least privilege can be enforced. Capability design and permission prompts add runtime complexity.

## Alternatives considered

Giving every plugin unrestricted process access was rejected because it makes trust boundaries meaningless.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


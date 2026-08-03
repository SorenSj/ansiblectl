# ADR-0015: Inventory Architecture

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

Ansible execution requires a reliable, explainable view of hosts and groups.

## Decision

Inventory is modelled as a validated domain concept resolved through provider ports. The application layer produces a canonical inventory representation for execution, preserving provenance and validation diagnostics where supported.

## Consequences

Multiple inventory sources can be added without changing use cases. Merge, precedence, and conflict rules require a dedicated Technical Specification before implementation.

## Alternatives considered

Treating inventory as an opaque file passed directly to Ansible was rejected because it prevents validation and provider composition.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


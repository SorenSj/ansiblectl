# ADR-0007: YAML Configuration Format

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

Ansible users expect human-editable declarative project configuration.

## Decision

YAML is the primary human-authored configuration format. The supported YAML subset will be documented: mappings, lists, scalars, and explicit schemas are allowed; custom tags, unsafe object construction, and behaviour hidden in YAML features are prohibited.

## Consequences

The format aligns with Ansible and is approachable to operators. Parsing must be safe and schema validation is mandatory.

## Alternatives considered

JSON is less ergonomic for maintained configuration; TOML and HCL are not adopted without a specific interoperability requirement.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


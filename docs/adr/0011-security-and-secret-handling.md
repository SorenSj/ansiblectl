# ADR-0011: Security and Secret Handling

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

The tool may access automation credentials and make high-impact infrastructure changes.

## Decision

Secrets are retrieved through explicit provider interfaces only when needed. They MUST NOT be stored in ordinary configuration, source control, logs, diagnostics, event payloads, or snapshots. Plugins receive least-privilege capabilities and declared permissions.

## Consequences

The default posture reduces accidental disclosure and limits plugin authority. Secret-provider contracts and redaction behaviour must be thoroughly tested.

## Alternatives considered

Treating secrets as ordinary configuration values was rejected because it normalises leakage into files and logs.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


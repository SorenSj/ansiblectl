# ADR-0030: Remote API Deferral

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-03 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0001](0001-architectural-style-and-governance.md) |

## Context

A future API may enable web interfaces and remote automation, but it is not required for the local-first product.

## Decision

The initial product exposes no REST, RPC, or hosted control-plane API. Application use cases are designed so a future delivery adapter can invoke them. Introducing a remote API requires an ADR covering authentication, authorisation, tenancy, transport, lifecycle, and compatibility.

## Consequences

The project avoids premature distributed-system and security complexity while preserving a future path. Remote callers initially use the documented CLI contract.

## Alternatives considered

Building a REST API alongside the first CLI was rejected because it duplicates surface area without a validated use case.

## Compliance

Implementation and documentation changes governed by this decision MUST be reviewed against the Engineering Principles and Architecture Handbook. A material revision requires a superseding ADR.


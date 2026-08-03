# TS-0009: Secret Provider Contract

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-03 |
| Related ADRs | [ADR index](../adr/README.md) |

## Purpose

Defines the minimum contract for resolving and redacting secret material without coupling the core to a backend.

## Scope

This specification defines the initial public and internal contract for this capability. Implementation details that do not alter the stated contract remain flexible.

## Functional requirements

1. A secret reference MUST identify provider and key without embedding the secret value.
2. Providers MUST return secret material only through a protected in-memory contract.
3. Secret retrieval MUST be auditable through safe metadata, not values.
4. A missing, denied, or malformed secret MUST produce a typed failure.
5. Providers MUST support test fakes without live credentials.

## Interfaces and data

The secret port resolves SecretReference to protected material for the minimum necessary operation; renderers and event payloads never receive that material.

## Verification

- A missing reference produces an actionable provider-aware error.
- Log capture proves secret values are redacted.
- A fake provider supports an execution test without network access.

## Non-goals

This specification does not introduce unrelated delivery mechanisms, hosted services, or public APIs beyond the contract described above.


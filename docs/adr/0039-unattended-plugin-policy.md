# ADR-0039: Unattended Plugin Policy

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-04 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0026](0026-plugin-permission-model.md), [ADR-0038](0038-signed-plugin-provenance-and-registry-trust.md), [TS-0022](../specifications/ts-0022-plugin-trust-verification.md) |

## Context

The initial permission model accepts explicit CLI grants. That is suitable for local preflight but
does not provide a reproducible decision for scheduled jobs, CI, or enterprise-managed hosts.
Unattended execution cannot safely prompt, infer approval from installation, or broaden grants
because a plugin was previously allowed interactively.

## Decision

Unattended plugin execution is default-deny and requires a versioned local policy. A matching rule
pins provider identity, allowed version or exact artifact digest, signing-key fingerprint,
distribution origins, and the maximum named permissions. Deny rules take precedence. Requested
permissions are granted only by intersection with the matching allow rule.

Non-interactive evaluation never prompts and never writes policy. Missing, unreadable, ambiguous,
or non-matching policy fails before plugin import with a stable reason. Policy files and trust keys
must be regular owner-controlled files inside an explicitly configured policy root; workspace
plugin content cannot modify or replace them through ansiblectl.

An audit operation may explain the safe decision using identities, versions, opaque fingerprints,
permission names, and stable reason codes. It must not expose signatures, keys, credentials,
artifact paths, environment values, or raw policy content. Audit mode does not authorize runtime
execution.

Policy layering is deterministic: managed deny rules, managed allow rules, then optional local
restrictions. A lower-precedence layer may remove authority but cannot add authority absent from a
managed allow rule.

## Consequences

- Scheduled and enterprise execution receives reproducible least-privilege decisions.
- Interactive grants no longer imply unattended authority.
- Managed policy deployment and file ownership become operator responsibilities.
- Policy explanation can remain useful without disclosing trust material.
- The first implementation is local policy evaluation, not a hosted policy control plane.

## Alternatives considered

Persisting interactive approvals was rejected because context and artifact identity can change.
Environment-variable grants were rejected because process environments are mutable and difficult
to audit safely. First-match rule evaluation was rejected because ordering mistakes could bypass a
later deny. A hosted policy dependency was rejected because it conflicts with the local-first and
offline execution posture.

## Compliance

TS-0022 defines the initial policy schema and decision contract. Any policy layer that can broaden
managed authority, interactive prompt in non-interactive mode, or network dependency requires a
superseding ADR.

# TS-0016: Policy Evaluation

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-03 |
| Related ADRs | [ADR index](../adr/README.md) |

## Purpose

Defines optional policy discovery, evaluation, findings, enforcement modes, and CLI presentation.

## Scope

This specification defines the initial public and internal contract for this capability. Implementation details that do not alter the stated contract remain flexible.

## Functional requirements

1. Policies MUST consume validated models and declared operation context.
2. Findings MUST include stable rule identifier, severity, message, affected location, and remediation when known.
3. Enforcement mode MUST be explicit: report, warn, or deny.
4. A deny finding MUST prevent the governed operation before irreversible work begins.
5. Policy evaluation MUST be deterministic for the same inputs and policy set.

## Interfaces and data

The policy service receives a typed EvaluationRequest and returns a PolicyReport with findings and enforcement outcome.

The initial evaluator sorts findings by rule identifier and affected location.
Its explicit modes are `report`, `warn`, and `deny`; only `deny` with one or
more findings blocks the governed operation before adapter invocation.

The initial bundled rule `ANSIBLECTL-APPLY-001` applies only to `run.apply`.
It emits a high-severity finding when the validated execution targeting has no
explicit host limit, with remediation to retry using `--limit`. The CLI
composition enables this rule by default. In the default `deny` enforcement
mode the finding prevents inventory materialization and adapter invocation;
`report` and `warn` preserve their documented non-blocking semantics.

The bundled rule `ANSIBLECTL-APPLY-002` emits a high-severity finding when
`run.apply` targets a dirty repository worktree. It does not apply to
`run.check`. Repository revision mismatch is a validation failure before policy
evaluation rather than an overridable finding.

## Verification

- The same inputs produce an identical ordered report.
- A deny rule blocks execution before adapter invocation.
- Machine-readable policy output validates against its schema.
- Apply without a host limit produces `ANSIBLECTL-APPLY-001`; check mode does not.
- The default CLI composition includes the bundled apply-limit rule.
- Dirty apply produces `ANSIBLECTL-APPLY-002`; dirty check mode does not.
- `run --preflight` presents the same deterministic policy report without invoking an adapter.

## Non-goals

This specification does not introduce unrelated delivery mechanisms, hosted services, or public APIs beyond the contract described above.

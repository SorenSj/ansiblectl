# TS-0008: Playbook Selection and Validation

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-03 |
| Related ADRs | [ADR index](../adr/README.md) |

## Purpose

Defines how a playbook is identified, located, and validated before it is executed.

## Scope

This specification defines the initial public and internal contract for this capability. Implementation details that do not alter the stated contract remain flexible.

## Functional requirements

1. A playbook identifier MUST resolve within the configured project or repository boundary.
2. Resolution MUST reject paths that escape the declared content root.
3. The system MUST verify existence and supported file type before execution.
4. Additional syntax or lint validation MAY be requested explicitly and MUST report tool provenance.
5. Selected playbook and revision MUST be recorded in the execution request.
6. The exact validated playbook file bytes MUST be identified by a SHA-256 digest before execution.
7. If the selected playbook becomes unreadable before its digest is calculated, execution MUST fail safely.
8. Persisted metadata MUST identify the selected playbook by a workspace-relative path and MUST NOT expose an absolute workspace path.

## Interfaces and data

The selection service returns a typed PlaybookReference containing canonical path, repository revision, and validation findings.

The initial selector accepts `.yml` and `.yaml` files only. Relative identifiers
are resolved against the declared content root, while absolute identifiers must
still be contained by it. The resulting reference stores the canonical path and
explicit repository revision; optional syntax/lint findings may be added later.

The execution request carries the digest as a `sha256:`-prefixed hexadecimal
value. The digest identifies the precise bytes validated for the run, including
dirty worktree content permitted in check mode; neither execution history nor
events copy the raw playbook content.

Execution results, events, and history pair that digest with the selected
playbook's POSIX-style path relative to the validated workspace root. If a
reference cannot be represented within that root, the safe path is omitted.
Older records without the relative path remain readable.

The CLI exposes selection validation as `playbook validate <path> --revision
<revision>`. Its result contains the workspace-relative path, revision, exact
byte digest, findings, and validator name/version. This command does not invoke
Ansible or claim syntax validation; explicit syntax/lint validation remains a
separate opt-in capability.

## Verification

- A relative path resolves reproducibly within a workspace.
- Traversal outside a content root is rejected.
- The execution request contains the canonical selected playbook.
- Changing any playbook byte changes the recorded digest.
- A playbook that becomes unreadable after selection is rejected before execution.
- Execution metadata reports `playbooks/site.yml`, not an absolute workspace path.
- Selection validation reports tool provenance without executing the playbook.

## Non-goals

This specification does not introduce unrelated delivery mechanisms, hosted services, or public APIs beyond the contract described above.

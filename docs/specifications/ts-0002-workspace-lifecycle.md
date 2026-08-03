# TS-0002: Workspace Lifecycle

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-03 |
| Related ADRs | [ADR index](../adr/README.md) |

## Purpose

Defines workspace discovery, initialisation, layout, selection, and isolation for project-scoped operations.

## Scope

This specification defines the initial public and internal contract for this capability. Implementation details that do not alter the stated contract remain flexible.

## Functional requirements

1. A workspace MUST be explicitly selected, discovered by documented rules, or initialised by a dedicated command.
2. Workspace metadata MUST have a versioned schema.
3. Commands that mutate project state MUST resolve and report the target workspace before mutation.
4. Relative paths MUST be resolved against the selected workspace, not the process current directory after resolution.
5. Workspace initialisation MUST be idempotent or fail without partial state.

## Interfaces and data

The workspace service accepts a path or selection policy and returns a validated Workspace model with canonical root and metadata locations.

The initial workspace layout is deliberately minimal:

```text
<workspace-root>/
└── .ansiblectl/
    └── workspace.json
```

`workspace.json` contains exactly one field, `schema_version`, initially set to
`1`. Discovery starts at the selected directory (or process directory when no
explicit selection is given) and walks its parents until this metadata file is
found. The `workspace init [PATH]` command creates this layout atomically; a
second invocation returns the existing valid workspace without changing it.

## Verification

- Initialising a new workspace creates only the documented layout.
- Running a project-scoped command outside a workspace produces a remediation message.
- Path traversal and writes outside the workspace are rejected unless explicitly allowed.

## Non-goals

This specification does not introduce unrelated delivery mechanisms, hosted services, or public APIs beyond the contract described above.

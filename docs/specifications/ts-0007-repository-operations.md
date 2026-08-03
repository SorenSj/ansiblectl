# TS-0007: Repository Operations

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-03 |
| Related ADRs | [ADR index](../adr/README.md) |

## Purpose

Defines repository discovery, clone, fetch, revision selection, synchronisation, and safe working-tree handling.

## Scope

This specification defines the initial public and internal contract for this capability. Implementation details that do not alter the stated contract remain flexible.

## Functional requirements

1. Repository operations MUST be scoped to a validated workspace path.
2. A requested revision MUST be explicit or resolved according to documented policy.
3. Mutating operations MUST report the repository and revision target before acting.
4. Credentials MUST be supplied through secret references or environment policy, never command arguments or logs.
5. Conflicts, dirty worktrees, and authentication failures MUST be classified and actionable.

## Interfaces and data

The repository port accepts a RepositoryRequest and returns typed state and operation results; Git is an adapter, not a public domain dependency.

The initial request requires absolute workspace and repository paths, with the
repository path contained by the workspace, and a non-empty explicit revision.
Before a future sync mutation, the adapter inspects `git status --porcelain`;
a dirty worktree is a typed failure that preserves user changes. Credentials
are intentionally absent from this request and adapter contract.

Execution preflight resolves both the requested revision and `HEAD` to commit
identifiers and requires equality before policy evaluation. Inspection reports
tracked and untracked workspace changes while excluding only Ansiblectl's own
`.ansiblectl` runtime directory.
The resolved commit identifier is propagated into the execution record rather
than relying on a mutable branch or tag label for later attribution.

For a clean repository, the initial Git sync runs fixed `git fetch --prune` and
`git checkout --detach REVISION` argument vectors. It reports the repository
and revision in the typed result; authentication remains external environment
policy rather than a command argument.
After checkout, the application inspects the repository again and requires the
resolved requested commit to equal `HEAD`. CLI results include both immutable
commit identifiers; a mismatch is an actionable failed sync.

The immutable commit identity can be supplied to
`execution list --resolved-revision` as an exact, read-only history filter;
requested branch and tag labels are not substituted for this attribution.

## Verification

- A fake repository port validates application orchestration.
- A dirty worktree failure does not overwrite user changes.
- Credentials are absent from rendered command diagnostics.
- Revision mismatch prevents execution and recommends repository synchronisation.
- Synchronisation verifies and reports the immutable post-checkout commit.
- A resolved immutable revision selects matching execution-history records exactly.

## Non-goals

This specification does not introduce unrelated delivery mechanisms, hosted services, or public APIs beyond the contract described above.

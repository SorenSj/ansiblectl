# TS-0017: State and Cache Management

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-03 |
| Related ADRs | [ADR index](../adr/README.md) |

## Purpose

Defines ownership, scope, invalidation, locking, and inspection of local persistent state and cache entries.

## Scope

This specification defines the initial public and internal contract for this capability. Implementation details that do not alter the stated contract remain flexible.

## Functional requirements

1. State MUST be scoped to a workspace or documented user-level location.
2. Each persistent format MUST contain a schema version.
3. Cache entries MUST declare their source identity and invalidation condition.
4. Cache corruption MUST fail safely and offer a recovery path.
5. Concurrent mutations MUST use documented locking or transactional replacement.
6. Interrupted filesystem transactions MUST remain discoverable and recoverable from durable,
   versioned journals.
7. Recovery MUST default to a read-only preview and require explicit application.

## Interfaces and data

The state port exposes typed reads, writes, invalidation, and inspection; callers do not access storage paths directly.

The initial workspace store uses `.ansiblectl/state.json`, with
`schema_version: 1` and named cache entries containing source identity and
invalidation condition. Writes use the transactional filesystem primitive. Corrupt or
unsupported state fails safely and instructs the operator to remove that file.
State paths are resolved inside the selected workspace, and symbolic links are
rejected before reads or writes.

`state show` exposes cache-entry names, source identities, and invalidation
conditions in human or schema-versioned JSON output. Stored cache values are
deliberately omitted because they may contain sensitive provider data.

`state invalidate <name>` previews removal of one exact cache entry by default.
`--apply` performs the read, removal, and atomic replacement while holding an
exclusive workspace-state lock; unrelated entries are retained.

`state recover` lists opaque identifiers for interrupted filesystem transactions without exposing
paths or contents. `state recover --apply` rolls back incomplete work in reverse order and cleans
completed journals. Corrupt journals are retained and fail with the stable
`FILESYSTEM_RECOVERY_REQUIRED` error code for manual inspection.

Execution event history is retained in the workspace's schema-versioned JSONL
log. `execution prune --keep N` previews removal by default; `--apply` rewrites
the log transactionally while holding the same advisory lock used by event writers.
Only output directories derived from removed execution identifiers are cleaned,
and unknown files are never recursively deleted.
Syntax-check executions are published to the same history with operation
`playbook.syntax_check`, so their private output directories participate in the
same retention lifecycle.

## Verification

- A corrupt cache is discarded or reported without corrupting workspace data.
- A schema-version mismatch follows documented migration or reset behaviour.
- Concurrent update tests preserve a valid final record.
- State inspection never renders stored cache values or follows symbolic links.
- State invalidation defaults to preview and applies only to one exact named entry.
- Transaction recovery defaults to preview, retains corrupt evidence, and applies only explicitly.
- Execution retention preserves the newest requested records and unrelated public events.

## Non-goals

This specification does not introduce unrelated delivery mechanisms, hosted services, or public APIs beyond the contract described above.

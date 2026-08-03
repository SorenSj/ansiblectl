# TS-0006: Inventory Resolution

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-03 |
| Related ADRs | [ADR index](../adr/README.md) |

## Purpose

Defines inventory source loading, validation, merge policy, provenance, and canonical execution representation.

## Scope

This specification defines the initial public and internal contract for this capability. Implementation details that do not alter the stated contract remain flexible.

## Functional requirements

1. Inventory sources MUST implement a provider contract.
2. Resolved hosts and groups MUST be validated before execution.
3. Conflicting values MUST follow a documented precedence policy or produce an error.
4. The resolved inventory MUST retain non-secret provenance where practical.
5. The execution adapter MUST receive a canonical generated representation rather than raw provider internals.

## Interfaces and data

The inventory service returns a typed ResolvedInventory with hosts, groups, variables, diagnostics, and provenance metadata.

The initial merge policy is low-to-high provider precedence: a later host with
the same name replaces the earlier definition and records a diagnostic naming
both sources. Groups may reference only resolved hosts. The generated adapter
input has sorted `hosts` with address and variables, plus sorted `groups` with
host-name lists; providers themselves are never passed to an execution adapter.
The materializer transforms that mapping into native Ansible YAML under
`all.hosts` and `all.children` without changing the canonical digest input.

The exact canonical mapping passed to the materializer is serialized as sorted,
compact UTF-8 JSON and identified by a `sha256:`-prefixed digest. The digest,
not raw inventory data, is retained in execution metadata and public events.
`inventory show` reports the same digest in human output and in its
`schema_version: 1` JSON contract, allowing preflight output to be matched to
execution history.
The digest can be supplied to `execution list --inventory-digest` as an exact,
read-only history filter.

The explicit `inventory validate` preflight resolves and materializes the same
canonical mapping, then invokes `ansible-inventory --list` with a controlled
timeout and environment. Validator output remains in private captured-output
files, while the CLI reports safe status, digest, and output references. The
execution history records the operation as `inventory.validate`.

## Verification

- Two providers with a declared precedence resolve predictably.
- An invalid host definition fails before execution.
- A fake provider can be used in application tests.
- Equivalent canonical mappings produce the same digest; content changes produce a different digest.
- Inventory inspection and execution metadata use the same canonical digest algorithm.
- Inventory inspection digests can select matching execution-history records exactly.
- Materialized inventory is valid native Ansible YAML and remains private and ephemeral.
- Explicit Ansible validation retains the canonical digest and private output references.

## Non-goals

This specification does not introduce unrelated delivery mechanisms, hosted services, or public APIs beyond the contract described above.

# Filesystem recovery runbook

| Field | Value |
| --- | --- |
| Status | Operational guidance |
| Version | 1.0 |
| Date | 2026-08-04 |

Use this runbook when `ansiblectl` reports an interrupted filesystem transaction. Recovery output
contains only opaque transaction identifiers, bounded ages, stable reason codes, and required
actions. Do not copy raw files from `.ansiblectl/transactions` into tickets or chat messages: the
journals contain local paths and operational metadata.

## Inspect without changing state

Run the safe preview first:

```console
ansiblectl --workspace WORKSPACE --output json state recover --details
```

Interpret each diagnostic as follows:

| Diagnostic | Meaning | Safe action |
| --- | --- | --- |
| `active_owner=true` | A live process owns the transaction. | Wait for that process to finish. Do not recover or delete it. |
| `action=rollback` | An inactive transaction may have partially changed targets. | Stop writers, then apply recovery. |
| `action=cleanup` | The durable operation finished, but its journal remains. | Apply recovery to remove the completed journal. |
| `action=manual_inspection` | The journal is corrupt, unreadable, or unsupported. | Preserve it, restrict access, and escalate to an operator. |

Age is diagnostic context only. Ansiblectl never expires recovery evidence automatically, and an
old journal is not proof that manual deletion is safe.

## Apply automatic recovery

Quiesce processes that write to the workspace, save the safe preview output, and run:

```console
ansiblectl --workspace WORKSPACE state recover --apply
```

Run the detailed preview again. A successful recovery leaves no inactive automatic-recovery
entries. Re-running recovery is safe and should report no additional rollback work.

## Repeated failure or corrupt evidence

Do not repeatedly delete or edit journal files. Keep the entire transaction directory owner-only,
record the ansiblectl version and the safe diagnostic, and investigate filesystem health and free
space before retrying. Raw journal inspection is a privileged local operation because paths and
metadata are outside the public redaction contract.

Manual deletion is intentionally outside the recovery command. Perform it only after an operator
has established the intended target state, captured any required evidence, and confirmed that no
process holds the owner lock. Ansiblectl cannot recover a transaction after its journal and backups
have been removed.

## Filesystem limitations

The v0.3 transaction adapter supports tested local POSIX filesystems with advisory `fcntl` locks,
atomic same-filesystem replacement, and file and directory syncing. It rejects unsupported
capabilities before user-target mutation. Network and userspace filesystems have no durability
guarantee under this contract. Windows requires a separate locking adapter and is not supported by
the POSIX implementation.

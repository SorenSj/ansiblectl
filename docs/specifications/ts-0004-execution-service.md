# TS-0004: Execution Service

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-03 |
| Related ADRs | [ADR index](../adr/README.md) |

## Purpose

Defines preparation, invocation, cancellation, result capture, and failure classification for Ansible executions.

## Scope

This specification defines the initial public and internal contract for this capability. Implementation details that do not alter the stated contract remain flexible.

## Functional requirements

1. An execution MUST be prepared from validated workspace, configuration, inventory, repository, and playbook inputs.
2. The adapter MUST receive an argument vector, working directory, and explicit environment policy; it MUST NOT construct an unvalidated shell command.
3. Each execution MUST receive a unique identifier.
4. The result MUST capture status, exit code, elapsed time, and safe output references.
5. Cancellation and timeout behaviour MUST be explicit and leave a diagnosable result.

## Interfaces and data

Application code submits an ExecutionRequest to an execution port and receives an ExecutionResult. The Ansible adapter is one implementation of that port.

The initial request contract contains a non-empty argument vector, an absolute
working directory, an explicit environment mapping, an optional positive
timeout, and a generated execution identifier. The local adapter invokes that
vector with shell execution disabled. Results classify `completed`, `failed`,
`timed_out`, or `cancelled`, retain the execution identifier and elapsed time,
and expose only output references (not raw process output). A cancellation
requested before a process starts returns `cancelled`; in-process cancellation
will be added with the asynchronous execution lifecycle.

The local adapter stores each non-empty captured stream below the workspace's
private `.ansiblectl/runs` area. Execution identifiers are transformed into
safe directory keys, output files use owner-only permissions, and CLI results
expose file references without echoing raw Ansible output. Partial output from
a timed-out process follows the same storage policy.

Completed execution metadata is inspectable through an execution-history port.
Records contain timestamp, identifier, classified status, exit code, elapsed
time, safe output references, and a safe diagnostic. History inspection never
dereferences captured output automatically.

When repository preflight is configured, execution requests, results, events,
and history retain both the requested revision label and the resolved commit
identifier. Older records without these fields remain readable.

Execution metadata also retains the SHA-256 digest of the exact canonical
inventory representation supplied to the inventory materializer. It does not
embed raw host variables or addresses in the execution record.

Execution requests, results, events, and history also retain the SHA-256 digest
of the exact validated playbook file bytes. This identifies dirty check-mode
content without embedding the playbook. Older records without either digest
remain readable.

The playbook digest is paired with a workspace-relative playbook path in
results, events, and history. Absolute workspace paths are not persisted, and
older records without this field remain readable.

Check-mode executions may carry validated optional targeting: one Ansible host
limit, task tags, and skipped task tags. The application layer emits these as
separate argument-vector elements, and completed execution events retain the
selection for later inspection. Targeting values are never shell commands.

Apply mode requires an explicit application-layer confirmation before input
resolution, policy evaluation, inventory materialization, or adapter invocation.
Confirmed apply requests are evaluated as `run.apply`; check requests are
evaluated as `run.check`. Execution events and history retain the selected mode.

The non-negative CLI verbosity count is converted to at most one explicit
Ansible argument (`-v`, `-vv`, and so on), never a shell fragment. Requests,
results, events, and history retain the numeric count; older records default to
zero.

An explicit `--diff` run option is passed as its own Ansible argument and is
retained as boolean metadata in requests, results, events, and history. Diff
content follows the private captured-output policy and is never embedded in
metadata. Older records default the field to `false`.

Every execution carries a non-empty operation identifier. Normal runs use
`run`; explicit syntax checks use `playbook.syntax_check`. The operation is
retained in results, events, and history, and older records default to `run`.

## Verification

- A fake execution port can verify a request without invoking a process.
- A timeout returns a classified failure and retains the execution identifier.
- Arguments containing spaces or special characters are passed safely without shell interpolation.
- Captured and partial timeout output is stored with owner-only permissions and returned by reference.
- Execution history lists records newest first and resolves one exact execution identifier.
- Host and tag targeting is passed as explicit arguments and retained in execution history.
- An unconfirmed apply request reaches neither policy nor the execution adapter.
- A confirmed apply request omits `--check` and remains subject to the policy gate.
- In the default deny mode, apply without an explicit host limit is blocked before materialization.
- Run preflight requires the requested Git revision at HEAD; default apply policy also requires a clean worktree.
- Execution history distinguishes the requested revision from the resolved immutable commit.
- Execution history identifies the canonical inventory by digest without exposing its contents.
- Execution history identifies the exact validated playbook bytes by digest without exposing their contents.
- Execution history identifies the selected playbook without exposing the absolute workspace path.
- Global verbosity reaches Ansible as a separate argument and remains inspectable in execution history.
- Diff mode reaches Ansible as a separate argument without embedding diff content in metadata.
- Execution history distinguishes playbook runs from syntax-check operations.

## Non-goals

This specification does not introduce unrelated delivery mechanisms, hosted services, or public APIs beyond the contract described above.

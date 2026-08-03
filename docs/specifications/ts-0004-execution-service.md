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

## Verification

- A fake execution port can verify a request without invoking a process.
- A timeout returns a classified failure and retains the execution identifier.
- Arguments containing spaces or special characters are passed safely without shell interpolation.

## Non-goals

This specification does not introduce unrelated delivery mechanisms, hosted services, or public APIs beyond the contract described above.


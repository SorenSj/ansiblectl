# TS-0001: CLI Foundation

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-03 |
| Related ADRs | [ADR index](../adr/README.md) |

## Purpose

Defines the command-line shell, command registration, lifecycle, help, global options, and exit-code boundary.

## Scope

This specification defines the initial public and internal contract for this capability. Implementation details that do not alter the stated contract remain flexible.

## Functional requirements

1. The package MUST expose one `ansiblectl` console entry point.
2. Every command MUST provide generated help and a stable command path.
3. Global options for workspace selection, verbosity, output format, and non-interactive execution MUST be handled before use-case invocation.
4. The CLI MUST construct application dependencies only in the composition root.
5. Commands MUST return documented exit codes and MUST NOT print from application or domain layers.

## Interfaces and data

Input is argv plus environment; output is human text by default or an explicit machine-readable result. Command handlers invoke typed application commands and map results to output and exit codes.

The stable `execution list` and `execution show <execution-id>` paths inspect
safe records from the selected workspace. They do not read or render referenced
Ansible stdout or stderr content.

`execution prune --keep <count>` previews retention. Destructive mutation
requires the additional explicit `--apply` flag.

## Verification

- `ansiblectl --help` lists top-level commands and global options.
- An invalid command or argument returns a non-zero documented exit code.
- A command test can replace the application service without starting external adapters.

## Non-goals

This specification does not introduce unrelated delivery mechanisms, hosted services, or public APIs beyond the contract described above.

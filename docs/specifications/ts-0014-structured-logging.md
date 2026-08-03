# TS-0014: Structured Logging

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-03 |
| Related ADRs | [ADR index](../adr/README.md) |

## Purpose

Defines structured log records, levels, correlation, redaction, and CLI verbosity behaviour.

## Scope

This specification defines the initial public and internal contract for this capability. Implementation details that do not alter the stated contract remain flexible.

## Functional requirements

1. Log records MUST include timestamp, level, event name, and correlation or execution identifier when available.
2. Log fields MUST be structured and safe for machine processing.
3. Secret values and known sensitive fields MUST be redacted before a sink receives a record.
4. Verbosity options MUST affect rendering or threshold, not the underlying business result.
5. Plugins MUST log through the SDK logger contract.

## Interfaces and data

The logging port accepts a typed LogEvent; sinks render console or configured destinations without changing event semantics.

The initial `LogEvent` schema contains ISO-8601 UTC timestamp, level, stable
event name, optional correlation identifier, and structured fields. Fields
named `secret`, `token`, `password`, `credential`, or `key` are redacted before
any sink receives a record. Plugins use the public `PluginLogger` protocol.

The local CLI composition records completed execution events as JSON Lines in
the workspace's private `.ansiblectl/logs/events.jsonl` file. The execution
identifier is used as the correlation identifier; directories and the log file
are restricted to the workspace owner.

## Verification

- A captured log record contains mandatory fields.
- A secret-like value is absent from all configured test sinks.
- Plugin logs carry plugin identity and execution correlation.
- A completed CLI execution appends a redacted, correlated JSON record to the private workspace log.

## Non-goals

This specification does not introduce unrelated delivery mechanisms, hosted services, or public APIs beyond the contract described above.

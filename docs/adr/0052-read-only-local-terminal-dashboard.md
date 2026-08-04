# ADR-0052: Read-Only Local Terminal Dashboard

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-04 |
| Decision makers | Ansiblectl maintainers |
| Related | [ADR-0031](0031-terminal-user-interface-deferral.md), [ADR-0030](0030-remote-api-deferral.md), [ADR-0028](0028-workspace-lifecycle-and-isolation.md), [ADR-0011](0011-security-and-secret-handling.md), [TS-0035](../specifications/ts-0035-read-only-local-terminal-dashboard.md) |

## Context

The command workflows and local application services now expose validated workspace execution
history and payload-free durable-consumer state. Operators can query them separately, but lack one
compact local view for answering whether recent executions succeeded and whether event consumers
are progressing. ADR-0031 deferred a TUI until those workflows were validated and required any
future interface to remain an adapter over application services.

A terminal interface can accidentally become a second control plane. Input handling, refresh,
terminal state, untrusted display values, cross-workspace discovery, and convenient action keys
would otherwise introduce authorization, tenancy, lifecycle, injection, and compatibility risks.

## Decision

Version 0.17 adds one local, foreground, read-only terminal dashboard. It is a presentation adapter
over existing query services and adds no application mutation, execution, event-delivery, plugin,
repository, configuration, or secret capability.

Identity is the effective operating-system user that invokes the process. Authorization is fixed to
the dashboard's closed read-only query set; there is no login, role, privilege change, delegation,
or configurable permission. One process opens exactly one explicitly resolved and validated
workspace. It cannot discover, aggregate, or switch workspaces.

The dashboard shows a bounded execution summary, bounded safe execution metadata, and payload-free
durable-consumer status. It never reads or displays captured stdout or stderr, diagnostics, event
envelopes or payloads, secrets, configuration values, repository content, absolute paths, or raw
exceptions. Dynamic values are converted to deterministic terminal-safe ASCII before layout.

The process requires interactive input and output terminals, enters terminal mode only after all
preflight checks and the initial snapshot succeed, and restores terminal state on every normal,
error, resize, interruption, and signal path. Refresh is explicit user input and reconstructs a
bounded snapshot; no polling thread, daemon, listener, session, or background process exists.

This decision narrowly supersedes ADR-0031 for the specified dashboard. Mutable terminal workflows,
remote callers, multi-workspace views, and every other TUI scope remain deferred. ADR-0030 remains
unchanged: the dashboard creates no remote API or hosted control plane.

## Consequences

- Operators gain a cohesive local operational view without a new control surface.
- Existing application query ports remain the source of truth and can be tested independently of
  terminal behavior.
- Manual refresh makes snapshot age visible and avoids an unattended lifecycle.
- Terminal capability and restoration become explicit fail-closed platform contracts.
- The deliberately small interaction model does not replace composable commands or machine output.

## Alternatives considered

A mutable TUI was rejected because action authorization, confirmations, concurrency, and recovery
need separate governance. Automatic polling was rejected because it adds scheduling, cancellation,
and continuous filesystem-read lifecycle. Cross-workspace discovery was rejected because it widens
tenancy and path disclosure. Reusing command subprocesses was rejected because parsing rendered
output duplicates the CLI boundary. A web or loopback interface was rejected because it creates an
inbound service and returns to the remote-API decision.

## Compliance

TS-0035 defines the command, identity, authorization, tenancy, snapshot, display, input, terminal
lifecycle, compatibility, redaction, and verification contracts. Any new action, automatic refresh,
workspace selection, data class, listener, or remote caller requires a new ADR and specification.

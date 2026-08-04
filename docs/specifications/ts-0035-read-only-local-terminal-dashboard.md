# TS-0035: Read-Only Local Terminal Dashboard

| Field | Value |
| --- | --- |
| Status | Normative |
| Version | 1.0 |
| Date | 2026-08-04 |
| Related ADRs | [ADR-0052](../adr/0052-read-only-local-terminal-dashboard.md), [ADR-0031](../adr/0031-terminal-user-interface-deferral.md), [ADR-0030](../adr/0030-remote-api-deferral.md), [ADR-0028](../adr/0028-workspace-lifecycle-and-isolation.md) |

## Purpose

Define a bounded local terminal dashboard for safe execution metadata and payload-free durable-event
consumer state without introducing a mutable or remote control plane.

## Command, identity, authorization, and tenancy

The public command is `ansiblectl dashboard`. It accepts the existing workspace selection context
and no dashboard-specific path, query, limit, interval, action, credential, plugin, or output option.
The resolved output mode MUST be `text`; JSON or YAML selection is a usage error before terminal
mode. Both stdin and stdout MUST be interactive terminals referring to the same foreground process
session. Redirects, pipes, files, sockets, pseudo-background sessions, and missing terminal
capabilities fail before terminal mutation.

The sole identity is the invoking process's effective operating-system user. The closed
authorization set is `StatusService.get_status`, `ExecutionHistoryService.summary`,
`ExecutionHistoryService.list(limit=100)`, and `EventOperationsService.inspect`. The adapter MUST NOT
call execution-history `retention`, durable-event `register`, `retry`, `abandon`, or `retention`, or
any execution, delivery, configuration-write, state-write, repository, inventory, policy, plugin,
secret, or external-process operation.

One invocation resolves and validates exactly one workspace before the initial snapshot. The
workspace identity is fixed for the process lifetime. The dashboard MUST NOT enumerate parent or
sibling directories, discover other workspaces, aggregate data, change working directory, or offer
workspace switching. It inherits the existing private workspace ownership and permission checks and
adds no cross-user, group, root, or privilege override.

## Snapshot and data contract

Each snapshot is built synchronously in this order: application status, execution summary, at most
100 newest execution records, then consumer status. A refresh either replaces the entire visible
snapshot after every query succeeds or retains the preceding snapshot and shows one stable,
value-free refresh-failure marker. Partial new data is never mixed with old data.

The status panel contains only the application version and fixed readiness message. The execution
summary contains total and canonical status and mode counts. Each execution row contains only
timestamp, execution identifier, status, operation, mode, exit code, and elapsed seconds. The
dashboard MUST NOT access or render stdout or stderr references, diagnostic, targeting, requested
or resolved revision, inventory or playbook digest, playbook path, verbosity, or diff fields.
Consumer rows contain only consumer identifier, event count, pending count, lowest pending sequence,
attempt count, next attempt time, and stable state.

Snapshot construction is bounded to 100 execution rows and 100 consumer rows. More than 100
consumer rows is a stable snapshot failure, not silent truncation. Counts use non-negative decimal
integers, elapsed time uses a fixed three-decimal representation, and absent optional scalars render
as `-`. Rows retain the deterministic order returned by their application service; the adapter does
not perform filesystem reads behind those ports or infer relationships between values.

## Display and redaction contract

The screen has three fixed panels: Status, Executions, and Consumers. Layout depends only on
terminal rows and columns and the bounded snapshot. At fewer than 80 columns or 24 rows, the screen
shows only a fixed minimum-size message and quit/refresh help. No dynamic value is rendered in that
state. Resizing recomputes layout from the current snapshot without querying services.

Every dynamic scalar is converted without invoking an unsupported object's `str` or `repr` and then
encoded as printable ASCII. ASCII graphic characters and spaces are retained; backslash, C0, DEL,
C1, escape, line separators, bidi controls, zero-width characters, non-ASCII, and invalid Unicode
are rendered as deterministic `\\xHH`, `\\uHHHH`, or `\\UHHHHHHHH` escapes. Cells are then truncated
only at escape-token boundaries with a visible ASCII `...` suffix. Dynamic bytes MUST NOT be written
to the terminal before this conversion. ANSI control sequences are fixed adapter constants only.

The dashboard never displays or records secrets, configuration values, environment, absolute or
relative paths, repository content, inventory, playbook content, host targeting, event identifiers,
event envelopes or payloads, captured output, diagnostics, claim tokens, socket or webhook details,
credentials, exception text, or tracebacks. Snapshot failures use only stable public error classes.
No screen content is copied into logs, events, execution history, durable state, crash files, or
clipboard integrations.

## Interaction and terminal lifecycle

The complete input vocabulary is:

- `q`, Escape, or end-of-input: quit;
- `r`: synchronously request one new snapshot;
- Tab or right arrow and Shift-Tab or left arrow: select the next or previous panel;
- up/down arrows or `k`/`j`: move the selected row within the current bounded panel.

All other complete keys are ignored. Partial and overlong escape sequences are discarded within a
fixed 32-byte input bound. Paste, mouse, focus, hyperlinks, OSC, device replies, function keys,
command text, search, filters, shell escape, clipboard, and free-form input are unsupported. Input
never becomes a query value.

Preflight and the initial snapshot complete before alternate-screen entry, raw input, cursor hiding,
or signal-handler installation. Thereafter one foreground thread owns input, rendering, resize, and
refresh. There is no timer, polling, worker, child process, listener, lock held while waiting for
input, persisted session, or resume state.

The adapter records the original terminal attributes and installs restoration before its first
terminal mutation. Restoration is idempotent and runs on normal quit, end-of-input, rendering or
query failure, `KeyboardInterrupt`, `SIGINT`, `SIGTERM`, and process-level cleanup. It restores the
original attributes, shows the cursor, disables adapter modes, leaves the alternate screen, and
writes no dynamic value. `SIGWINCH` only marks a pending resize for the foreground loop. Unsupported
signal or terminal capabilities fail closed before entry.

Clean quit returns `0`; interruption returns `130`; preflight, snapshot, capability, input, and
rendering failures use the existing stable CLI error mapping after restoration. The adapter writes
interactive frames only to stdout and safe errors only after leaving terminal mode.

## Compatibility contract

The dashboard is additive. Existing commands, text/JSON/YAML envelopes, services, SDK imports,
schemas, history, event bytes, delivery adapters, configuration, logs, and exit codes retain exact
behavior. The dashboard does not declare a machine-readable or screen-layout compatibility API.
Keys, permitted fields, authorization boundaries, and redaction are normative; presentation spacing
and color are not. Color cannot be required to understand state and obeys the existing no-color
environment behavior.

## Verification

- Boundary tests prove only the closed query set is reachable and mutation ports are never composed
  into the dashboard adapter.
- Workspace tests prove one validated workspace, fixed identity, no discovery or switching, and
  rejection before terminal entry.
- Snapshot tests prove ordering, atomic refresh, exact field allowlists, both 100-row bounds, and no
  output, diagnostic, targeting, path, digest, revision, payload, or secret access.
- Exhaustive display vectors cover C0, DEL, C1, escape, Unicode controls, bidi, zero width, invalid
  Unicode, token-boundary truncation, and arbitrary terminal sizes without control injection.
- Pseudo-terminal tests cover every key, partial and overlong input, EOF, resize, small terminals,
  redirected streams, and deterministic navigation.
- Subprocess tests terminate before entry and after every terminal mutation and query boundary,
  proving exact restoration for quit, failures, `SIGINT`, `SIGTERM`, and `KeyboardInterrupt`.
- Public-surface tests prove forbidden values remain absent from frames, safe errors, logs, events,
  history, durable bytes, and exception representations.
- Hosted CI passes on Ubuntu and macOS with Python 3.12, 3.13, and 3.14 without external network
  access.

## Non-goals

- Applying, running, retrying, abandoning, retaining, registering, editing, configuring, approving,
  installing, or invoking any mutation or external process.
- Automatic refresh, live output, event payloads, logs, diagnostics, diffs, playbook or inventory
  content, search, filters, details, command palettes, shell, plugins, mouse, paste, or clipboard.
- Multiple workspaces, discovery, switching, shared sessions, cross-user access, privilege changes,
  background processes, daemons, listeners, remote callers, inbound APIs, web interfaces, or hosted
  control planes.
- A stable screen layout, machine-readable dashboard output, terminal multiplexing guarantees,
  Windows support, or replacing composable CLI commands.

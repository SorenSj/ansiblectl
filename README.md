# ansiblectl

A local-first command-line platform for managing Ansible automation. The
project is in its initial foundation phase; its public CLI and SDK are
experimental during the 0.x release series.

## Development

The source package uses a `src/` layout. Python 3.12 through 3.14 are
supported on Ubuntu and macOS by the CI matrix. Transactional persistence additionally requires
the local filesystem capabilities documented in the
[recovery runbook](docs/operations/filesystem-recovery.md). See
[CONTRIBUTING.md](CONTRIBUTING.md) for the required local checks.

```console
uv sync --all-groups --locked
uv run ansiblectl --help
uv run ansiblectl status
```

## Workspace quick start

An ansiblectl workspace is an explicit local boundary for automation state.
Initialise one before using project-scoped commands:

```console
uv run ansiblectl workspace init ~/automation/example
uv run ansiblectl --workspace ~/automation/example workspace show
```

This creates only `.ansiblectl/workspace.json` beneath the selected workspace.

Inspect effective configuration and source provenance without exposing secret
references:

```console
uv run ansiblectl --workspace ~/automation/example config show
uv run ansiblectl --workspace ~/automation/example --output json config show
```

Inspect cache provenance and invalidation metadata without printing cached
values:

```console
uv run ansiblectl --workspace ~/automation/example state show
uv run ansiblectl --workspace ~/automation/example state invalidate inventory
uv run ansiblectl --workspace ~/automation/example state invalidate inventory --apply
uv run ansiblectl --workspace ~/automation/example state recover
uv run ansiblectl --workspace ~/automation/example state recover --apply
```

Resolve and inspect the currently configured inventory in human or stable JSON
form:

```yaml
# ~/automation/example/inventory/hosts.yml
all:
  children:
    web:
      hosts:
        web-1:
          ansible_host: 192.0.2.10
          ansible_port: 22
```

```console
uv run ansiblectl --workspace ~/automation/example inventory show
uv run ansiblectl --workspace ~/automation/example \
  --output json inventory show
uv run ansiblectl --workspace ~/automation/example inventory validate
```

The global machine-output interface is `--output json` or `--output yaml`.
`ANSIBLECTL_OUTPUT` can select the default. The older `--output-format`
spelling remains available only for migration compatibility.

The default source is `inventory/hosts.yml` inside the workspace. Select a
different YAML file inside the same boundary with `inventory show --source`.
The reported canonical digest can be matched against execution history.
`inventory validate` materializes that same canonical model privately and runs
`ansible-inventory --list`; captured inventory output is returned only by file
reference and the validation is recorded as operation `inventory.validate`.

## Repository operations

Inspect a repository inside the selected workspace at an explicit revision:

```console
uv run ansiblectl --workspace ~/automation/example \
  repository inspect repository --revision main
```

Synchronisation reports its target before fetching and checking out the
revision. It refuses to modify a dirty worktree, then verifies and reports the
resolved commit and post-checkout `HEAD`:

```console
uv run ansiblectl --workspace ~/automation/example \
  repository sync repository --revision release-1
```

## Plugin manifests

Validate one provider manifest, list explicitly selected manifests, or discover
all direct YAML manifests in the workspace's `plugins` directory without
loading plugin code:

```console
uv run ansiblectl --workspace ~/automation/example \
  plugin validate plugins/example.yaml
uv run ansiblectl --workspace ~/automation/example \
  plugin list --manifest plugins/example.yaml --manifest plugins/other.yaml
uv run ansiblectl --workspace ~/automation/example plugin discover
uv run ansiblectl --workspace ~/automation/example \
  plugin permissions plugins/example.yaml --grant network
```

Permission preflight is default-deny and does not initialise plugin code.

## Check-mode execution

Validate playbook selection, boundaries, file type, readability, and exact-byte
digest without executing Ansible:

```console
uv run ansiblectl --workspace ~/automation/example \
  playbook validate playbooks/site.yml --revision main
```

The result includes validator provenance. It is selection validation, not an
Ansible syntax check.

Request Ansible syntax validation explicitly when needed:

```console
uv run ansiblectl --workspace ~/automation/example \
  playbook validate playbooks/site.yml --revision main --syntax-check
```

Syntax-check output is stored privately and returned by reference rather than
embedded in terminal or JSON output.
Syntax checks are recorded with operation `playbook.syntax_check`, allowing
`execution list/show/prune` to inspect and retain their output safely.
Filter mixed history without changing it:

```console
uv run ansiblectl --workspace ~/automation/example \
  execution list --operation playbook.syntax_check
uv run ansiblectl --workspace ~/automation/example \
  execution list --mode apply --status failed --limit 10
```

The exact operation, classified status, and check/apply mode filters can be
combined to locate, for example, only failed apply executions without reading
captured stdout or stderr. A positive `--limit` returns only the newest
matching records without changing retention.

Copy the canonical digest from `inventory show` or `inventory validate` into
`execution list --inventory-digest sha256:...` to find only executions that
used that exact resolved inventory representation.
Likewise, copy the digest from `playbook validate` or `run --preflight` into
`execution list --playbook-digest sha256:...` to match the exact validated
playbook bytes.
The immutable commit reported by `repository inspect` or `run --preflight` can
be matched with `execution list --resolved-revision <object-id>`; branch and tag
labels are intentionally not used for this filter.
Use `execution list --playbook-path playbooks/site.yml` to select the same safe
workspace-relative playbook path reported by validation and execution output.

Get a compact operational overview without output references or captured
Ansible data:

```console
uv run ansiblectl --workspace ~/automation/example execution summary
```

The versioned result counts records by classified status, check/apply mode, and
stable operation identifier.

Ansiblectl isolates Ansible's controller-side temporary files below the
workspace's owner-only `.ansiblectl/tmp` directory instead of relying on
`~/.ansible/tmp`. Captured process output remains below `.ansiblectl/runs`;
symlinks cannot redirect those private logs outside the workspace.

Every run first validates the same effective configuration shown by
`config show`; invalid configuration stops the workflow before Ansible starts.
It then validates workspace inputs, generates a private canonical inventory,
and invokes Ansible with an explicit timeout and argument vector:

```console
uv run ansiblectl --workspace ~/automation/example run \
  --playbook playbooks/site.yml --revision main \
  --inventory inventory/hosts.yml --check --timeout 300 --policy-mode deny \
  --limit 'web:&staging' --tags deploy,config --skip-tags slow
```

Add `--preflight` to either `--check` or `--apply` to perform the same
configuration, playbook, inventory, repository, digest, targeting, and policy
checks without materializing inventory or starting Ansible. Apply preflight
does not require `--confirm`; an actual apply still does.

Add global `-v`, `-vv`, or higher before `run` to increase Ansible verbosity.
The numeric level is retained in execution output and history.
Add `--diff` to request Ansible before-and-after differences. Diff mode is
recorded, while the potentially sensitive diff content remains only in the
private captured-output files.

Ansible tasks can explicitly disable check mode. Review playbooks before
execution; `--check` is not an absolute guarantee that no remote changes occur.
Policy mode defaults to `deny`; `report` and `warn` retain findings but allow
execution to continue.

To apply changes, replace `--check` with `--apply --confirm` and provide an
explicit `--limit`. Apply mode is evaluated separately by policy and the
selected mode is retained in execution history. Omitting either apply flag
fails before workspace access; the default deny policy blocks apply without a
host limit before inventory materialization or execution.

Before either mode runs, the workspace Git repository must resolve the supplied
revision to the current `HEAD`. Default apply policy additionally requires a
clean worktree; Ansiblectl's own `.ansiblectl` runtime files are excluded from
that dirty-state calculation.

Run output and `execution list/show` distinguish the supplied revision label
from its resolved immutable Git commit, making later attribution independent of
branch or tag movement.

The same records include a SHA-256 digest of the canonical inventory supplied
to Ansible. This proves which inventory representation was used without copying
host addresses or variables into execution history.

They also include a SHA-256 digest of the exact validated playbook bytes. This
distinguishes the content actually used by a check-mode run even when the
playbook has uncommitted changes, without copying its contents into history.
The digest is shown with the workspace-relative playbook path; absolute local
workspace paths are not stored in execution history.

Captured Ansible output is not echoed directly. Non-empty stdout and stderr are
stored with owner-only permissions below `.ansiblectl/runs`, and the command
returns their file references for diagnosis.

Completed runs return exit code `0`, failed or timed-out external tools return
`5`, and a classified cancellation returns `130` in every output mode.
Unexpected internal failures are redacted at the installed CLI boundary and
return `1`; Python exception details are not printed to normal command output.
Invalid command syntax returns `2`, while parsed arguments that violate an
application contract return `4`. In JSON and YAML modes failures produce one
redacted structured document instead of argparse usage text, so supplied
argument values are not echoed into automation logs.
The same structured validation contract applies when `--apply` and `--confirm`
are not supplied together.
Policy-denied run preparation or execution returns `6`. Other typed failures
use the stable exit-code registry documented in
[TS-0005](docs/specifications/ts-0005-output-errors-and-exit-codes.md).
Workspace, inventory, repository, plugin, and execution-history failures follow
the same contract. Repository sync progress is suppressed in machine modes.

Completed runs also append a redacted structured record to
`.ansiblectl/logs/events.jsonl`, correlated by execution identifier.

Inspect safe execution metadata later without automatically printing captured
Ansible output:

```console
uv run ansiblectl --workspace ~/automation/example execution list
uv run ansiblectl --workspace ~/automation/example execution show <execution-id>
```

Preview retention, then explicitly apply the same policy:

```console
uv run ansiblectl --workspace ~/automation/example execution prune --keep 100
uv run ansiblectl --workspace ~/automation/example execution prune --keep 100 --apply
```

Operate durable public-event delivery without exposing event payloads. Registration is idempotent;
retry and abandon require an exact sequence and event identifier. Abandonment and retention are
preview-only unless `--apply` is supplied:

```console
uv run ansiblectl --workspace ~/automation/example event consumer register audit --start-sequence 1
uv run ansiblectl --workspace ~/automation/example event consumer inspect
uv run ansiblectl --workspace ~/automation/example event consumer retry audit \
  --sequence 7 --event-id <event-id>
uv run ansiblectl --workspace ~/automation/example event consumer abandon audit \
  --sequence 7 --event-id <event-id>
uv run ansiblectl --workspace ~/automation/example event retention
uv run ansiblectl --workspace ~/automation/example event retention --apply
```

Configure an outbound HTTPS endpoint privately in `.ansiblectl/webhooks.yaml`. The URL hostname
must also appear in its explicit allowlist:

```yaml
schema_version: 1
endpoints:
  audit:
    url: https://hooks.example.test/events
    allowed_hostnames: [hooks.example.test]
    bearer_secret: env:ANSIBLECTL_WEBHOOK_TOKEN
    connect_timeout_seconds: 10
    read_timeout_seconds: 30
```

Run one foreground delivery batch with a positive bound of at most 100 events:

```console
ANSIBLECTL_WEBHOOK_TOKEN='<injected-by-your-secret-manager>' \
  uv run ansiblectl --workspace ~/automation/example \
  event deliver audit --endpoint audit --max-events 10
```

Alternatively, deliver to one logical workspace-private archive. The identifier is never a path;
each event becomes one immutable mode-`0600` canonical JSON file below the fixed private archive
root:

```console
uv run ansiblectl --workspace ~/automation/example \
  event deliver local-audit --archive audit.primary --max-events 10
```

The command follows no redirects and performs no polling, background scheduling, automatic
abandonment, or automatic retention. Authentication and signing accept canonical `env:NAME` or
`file:NAME` references. Environment names may contain up to 128 uppercase ASCII letters, digits,
and underscores; file names use the same alphabet with a 64-character bound.

File references resolve only `.ansiblectl/secrets/NAME`. Provision `.ansiblectl` and its `secrets`
directory with mode `0700`, and each secret as an owner-only, single-link regular file with mode
`0600`. Content must be non-empty UTF-8 of at most 8 KiB without a terminal newline or other
control character. The secrets directory is excluded by the repository `.gitignore`; operators
must also exclude it from backups and securely manage provisioning, rotation, and deletion.

The selected provider is resolved exactly once per reference and attempt without enumeration,
trimming, caching, or fallback. Material is used only for the immediate request and is never placed
in workspace configuration, command output, logs, events, retry state, or durable state. Missing,
malformed, unsafe, or unsupported material fails before DNS or network activity.

Schema version 5 can opt into a timestamp-bound v2 signature by combining `signature_secret` with
`signature_version: 2`. Each attempt sends fixed `X-Ansiblectl-Timestamp` and
`X-Ansiblectl-Signature: v2=...` headers. Receivers should validate the authenticated Unix-second
timestamp against a bounded clock-skew policy and separately deduplicate the event identifier;
timestamps alone do not provide exactly-once delivery or replay state.

Private receivers require endpoint schema version 2 and a separately named policy in
`.ansiblectl/webhook-network-policies.yaml`:

```yaml
schema_version: 1
policies:
  automation-receivers:
    allowed_cidrs: [10.20.0.0/16, fd12:3456::/48]
```

The endpoint references the policy by name; CIDRs are never accepted on the command line:

```yaml
schema_version: 2
endpoints:
  audit:
    url: https://hooks.internal.example/events
    allowed_hostnames: [hooks.internal.example]
    network_policy: automation-receivers
```

Every DNS answer must belong to the named ranges. Mixed, loopback, link-local, metadata,
carrier-grade NAT, mapped, malformed, or out-of-policy answers fail before connection. HTTPS still
uses the platform trust store and the original hostname; the policy grants reachability, not server
identity trust.

## Project governance

The repository is the authoritative source for Ansiblectl's normative
engineering documentation. The initial governing document is
[Engineering Principles v1.0](docs/engineering-principles/engineering-principles-v1.0.md).

Supporting architecture, decision, specification, and diagram artefacts live
under [`docs/`](docs/).

Completed, active, and deferred release milestones are tracked in the
[project roadmap](docs/roadmap/README.md).

Operational recovery procedures and filesystem limitations are documented in the
[filesystem recovery runbook](docs/operations/filesystem-recovery.md).

# ansiblectl

A local-first command-line platform for managing Ansible automation. The
project is in its initial foundation phase; its public CLI and SDK are
experimental during the 0.x release series.

## Development

The source package uses a `src/` layout. Python 3.12 through 3.14 are
supported. See [CONTRIBUTING.md](CONTRIBUTING.md) for the required local checks.

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
uv run ansiblectl --workspace ~/automation/example --output-format json config show
```

Inspect cache provenance and invalidation metadata without printing cached
values:

```console
uv run ansiblectl --workspace ~/automation/example state show
uv run ansiblectl --workspace ~/automation/example state invalidate inventory
uv run ansiblectl --workspace ~/automation/example state invalidate inventory --apply
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
  --output-format json inventory show
uv run ansiblectl --workspace ~/automation/example inventory validate
```

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

Completed runs return exit code `0`, failed or timed-out runs return `1`, and a
classified cancellation returns `3` in both human and JSON output modes.
Unexpected internal failures are redacted at the installed CLI boundary and
return `70`; Python exception details are not printed to normal command output.
Invalid arguments return `2`. In JSON mode they produce one redacted structured
document instead of argparse usage text, so supplied argument values are not
echoed into automation logs.
The same structured validation contract applies when `--apply` and `--confirm`
are not supplied together.
Expected run-preparation failures return `1` as a structured
`operational_failure` in JSON mode and as an actionable stderr message in human
mode.
Workspace, inventory, repository, plugin, and execution-history failures follow
the same contract. Repository sync progress is suppressed in JSON mode.

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

## Project governance

The repository is the authoritative source for Ansiblectl's normative
engineering documentation. The initial governing document is
[Engineering Principles v1.0](docs/engineering-principles/engineering-principles-v1.0.md).

Supporting architecture, decision, specification, and diagram artefacts live
under [`docs/`](docs/).

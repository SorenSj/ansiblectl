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
```

The default source is `inventory/hosts.yml` inside the workspace. Select a
different YAML file inside the same boundary with `inventory show --source`.

## Repository operations

Inspect a repository inside the selected workspace at an explicit revision:

```console
uv run ansiblectl --workspace ~/automation/example \
  repository inspect repository --revision main
```

Synchronisation reports its target before fetching and checking out the
revision. It refuses to modify a dirty worktree:

```console
uv run ansiblectl --workspace ~/automation/example \
  repository sync repository --revision release-1
```

## Plugin manifests

Validate one provider manifest or list several validated descriptors without
loading plugin code:

```console
uv run ansiblectl --workspace ~/automation/example \
  plugin validate plugins/example.yaml
uv run ansiblectl --workspace ~/automation/example \
  plugin list --manifest plugins/example.yaml --manifest plugins/other.yaml
```

## Check-mode execution

Validate workspace inputs, generate a private canonical inventory, and invoke
Ansible with an explicit timeout and argument vector:

```console
uv run ansiblectl --workspace ~/automation/example run \
  --playbook playbooks/site.yml --revision main \
  --inventory inventory/hosts.yml --check --timeout 300 --policy-mode deny
```

Ansible tasks can explicitly disable check mode. Review playbooks before
execution; `--check` is not an absolute guarantee that no remote changes occur.
Policy mode defaults to `deny`; `report` and `warn` retain findings but allow
execution to continue.

Captured Ansible output is not echoed directly. Non-empty stdout and stderr are
stored with owner-only permissions below `.ansiblectl/runs`, and the command
returns their file references for diagnosis.

Completed runs also append a redacted structured record to
`.ansiblectl/logs/events.jsonl`, correlated by execution identifier.

Inspect safe execution metadata later without automatically printing captured
Ansible output:

```console
uv run ansiblectl --workspace ~/automation/example execution list
uv run ansiblectl --workspace ~/automation/example execution show <execution-id>
```

## Project governance

The repository is the authoritative source for Ansiblectl's normative
engineering documentation. The initial governing document is
[Engineering Principles v1.0](docs/engineering-principles/engineering-principles-v1.0.md).

Supporting architecture, decision, specification, and diagram artefacts live
under [`docs/`](docs/).

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

## Project governance

The repository is the authoritative source for Ansiblectl's normative
engineering documentation. The initial governing document is
[Engineering Principles v1.0](docs/engineering-principles/engineering-principles-v1.0.md).

Supporting architecture, decision, specification, and diagram artefacts live
under [`docs/`](docs/).

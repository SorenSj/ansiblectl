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

```console
uv run ansiblectl inventory show
uv run ansiblectl --output-format json inventory show
```

Until inventory providers are configured, the composition root returns an
empty, valid inventory.

## Project governance

The repository is the authoritative source for Ansiblectl's normative
engineering documentation. The initial governing document is
[Engineering Principles v1.0](docs/engineering-principles/engineering-principles-v1.0.md).

Supporting architecture, decision, specification, and diagram artefacts live
under [`docs/`](docs/).

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

## Project governance

The repository is the authoritative source for Ansiblectl's normative
engineering documentation. The initial governing document is
[Engineering Principles v1.0](docs/engineering-principles/engineering-principles-v1.0.md).

Supporting architecture, decision, specification, and diagram artefacts live
under [`docs/`](docs/).

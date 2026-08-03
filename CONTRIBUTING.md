# Contributing to Ansiblectl

Material changes must reference the applicable requirement, ADR, or Technical
Specification. Keep changes small, add automated verification at the relevant
layer, and update public-contract or contributor documentation in the same
change.

## Local quality checks

Install the supported Python version and [uv](https://docs.astral.sh/uv/), then
run the same required checks as CI:

```console
uv sync --all-groups --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
uv run python -m tools.validate_docs
uv run python -m tools.check_architecture
uv run python -m tools.validate_release
uv build
```

The supported runtime matrix is Python 3.12 through 3.14. `uv.lock` records
the reviewed, reproducible dependency resolution for these commands.

## Review checklist

- Link the relevant requirement, ADR, or TS.
- Include tests for changed behaviour, including a regression test for a bug.
- Confirm CLI/SDK compatibility and migration guidance when public contracts change.
- Run every local quality check above.
- Record any temporary exception with an owner, scope, rationale, and expiry or removal plan.

## Temporary exception example

- Owner: `maintainer-on-call`
- Scope: A one-time documentation-link validation exception for an external outage.
- Rationale: The external documentation host is unavailable and the change must restore an
  unrelated security fix.
- Expiry or removal plan: Re-run validation and remove this exception within two business days.

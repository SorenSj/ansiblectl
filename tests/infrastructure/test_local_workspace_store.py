"""Filesystem-adapter contract tests for workspace metadata."""

import json
from pathlib import Path

import pytest

from ansiblectl.domain.errors import WorkspaceNotFoundError, WorkspaceValidationError
from ansiblectl.infrastructure.local_workspace_store import LocalWorkspaceStore


def test_initialize_creates_only_the_documented_workspace_layout(tmp_path: Path) -> None:
    root = tmp_path / "workspace"

    workspace = LocalWorkspaceStore().initialize(root)

    assert workspace.root == root
    assert json.loads((root / ".ansiblectl/workspace.json").read_text()) == {"schema_version": 1}
    assert sorted(path.relative_to(root) for path in root.rglob("*")) == [
        Path(".ansiblectl"),
        Path(".ansiblectl/workspace.json"),
    ]


def test_initialize_is_idempotent(tmp_path: Path) -> None:
    store = LocalWorkspaceStore()
    root = tmp_path / "workspace"
    first = store.initialize(root)

    assert store.initialize(root) == first


def test_load_returns_existing_valid_workspace(tmp_path: Path) -> None:
    store = LocalWorkspaceStore()
    workspace = store.initialize(tmp_path)

    assert store.load(tmp_path) == workspace


def test_load_rejects_unknown_or_invalid_workspace(tmp_path: Path) -> None:
    store = LocalWorkspaceStore()
    with pytest.raises(WorkspaceNotFoundError):
        store.load(tmp_path)

    metadata = tmp_path / ".ansiblectl"
    metadata.mkdir()
    (metadata / "workspace.json").write_text('{"schema_version": 2}', encoding="utf-8")
    with pytest.raises(WorkspaceValidationError, match="unsupported"):
        store.load(tmp_path)


def test_initialize_refuses_ambiguous_existing_metadata_directory(tmp_path: Path) -> None:
    (tmp_path / ".ansiblectl").mkdir()

    with pytest.raises(WorkspaceValidationError, match="already exists"):
        LocalWorkspaceStore().initialize(tmp_path)

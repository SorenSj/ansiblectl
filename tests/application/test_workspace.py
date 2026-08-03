"""Workspace use-case tests with an explicit fake port."""

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from ansiblectl.application.workspace import WorkspaceService
from ansiblectl.domain.errors import WorkspaceNotFoundError
from ansiblectl.domain.events import Event, EventBus
from ansiblectl.domain.workspace import Workspace


@dataclass
class FakeWorkspaceStore:
    workspaces: dict[Path, Workspace] = field(default_factory=dict)
    initialized: list[Path] = field(default_factory=list)

    def load(self, root: Path) -> Workspace:
        try:
            return self.workspaces[root]
        except KeyError as error:
            raise WorkspaceNotFoundError("not found") from error

    def initialize(self, root: Path) -> Workspace:
        self.initialized.append(root)
        return self.workspaces[root]


def test_resolve_discovers_a_parent_workspace(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    nested = root / "repository" / "playbooks"
    nested.mkdir(parents=True)
    workspace = Workspace(
        root=root.resolve(), metadata_path=root / ".ansiblectl/workspace.json", schema_version=1
    )
    service = WorkspaceService(FakeWorkspaceStore(workspaces={root.resolve(): workspace}))

    assert service.resolve(None, nested) == workspace


def test_resolve_outside_a_workspace_has_remediation(tmp_path: Path) -> None:
    service = WorkspaceService(FakeWorkspaceStore())

    with pytest.raises(WorkspaceNotFoundError, match="workspace init"):
        service.resolve(None, tmp_path)


def test_initialize_canonicalizes_the_explicit_target(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    workspace = Workspace(
        root=root.resolve(), metadata_path=root / ".ansiblectl/workspace.json", schema_version=1
    )
    store = FakeWorkspaceStore(workspaces={root.resolve(): workspace})

    assert WorkspaceService(store).initialize(root) == workspace
    assert store.initialized == [root.resolve()]


def test_initialization_event_is_published_after_workspace_creation(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    workspace = Workspace(
        root=root.resolve(), metadata_path=root / ".ansiblectl/workspace.json", schema_version=1
    )
    delivered: list[Event] = []

    WorkspaceService(
        FakeWorkspaceStore(workspaces={root.resolve(): workspace}), EventBus([delivered.append])
    ).initialize(root)

    assert delivered == [Event("workspace.initialized", {"workspace": str(root.resolve())})]

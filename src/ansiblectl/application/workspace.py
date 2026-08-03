"""Workspace lifecycle use cases."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ansiblectl.domain.errors import WorkspaceNotFoundError
from ansiblectl.domain.workspace import Workspace, WorkspaceStore


@dataclass(frozen=True)
class WorkspaceService:
    """Coordinate workspace selection and lifecycle through an explicit port."""

    store: WorkspaceStore

    def initialize(self, path: Path) -> Workspace:
        """Initialise a workspace at an explicit target path."""

        return self.store.initialize(path.resolve())

    def resolve(self, explicit_path: Path | None, current_directory: Path) -> Workspace:
        """Resolve an explicit workspace or discover one by walking upward."""

        if explicit_path is not None:
            return self.store.load(explicit_path.resolve())
        candidate = current_directory.resolve()
        for root in (candidate, *candidate.parents):
            try:
                return self.store.load(root)
            except WorkspaceNotFoundError:
                continue
        raise WorkspaceNotFoundError(
            "No Ansiblectl workspace was found. Run 'ansiblectl workspace init' "
            "or select one with --workspace PATH."
        )

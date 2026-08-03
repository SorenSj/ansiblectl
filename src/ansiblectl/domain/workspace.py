"""Workspace domain model and its persistence port."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

WORKSPACE_DIRECTORY = ".ansiblectl"
WORKSPACE_METADATA_FILENAME = "workspace.json"
WORKSPACE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Workspace:
    """A validated local operating boundary for Ansiblectl."""

    root: Path
    metadata_path: Path
    schema_version: int


class WorkspaceStore(Protocol):
    """Port for loading and creating workspace metadata."""

    def load(self, root: Path) -> Workspace:
        """Load valid workspace metadata at an already canonical root."""

    def initialize(self, root: Path) -> Workspace:
        """Create or return a valid workspace at an already canonical root."""

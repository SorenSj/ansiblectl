"""Local filesystem adapter for the versioned workspace layout."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from ansiblectl.domain.errors import WorkspaceNotFoundError, WorkspaceValidationError
from ansiblectl.domain.workspace import (
    WORKSPACE_DIRECTORY,
    WORKSPACE_METADATA_FILENAME,
    WORKSPACE_SCHEMA_VERSION,
    Workspace,
)


class LocalWorkspaceStore:
    """Read and initialise workspaces without writing outside their root."""

    def load(self, root: Path) -> Workspace:
        """Load the workspace metadata from *root* or raise an expected error."""

        metadata_path = _metadata_path(root)
        if not metadata_path.is_file():
            raise WorkspaceNotFoundError(f"'{root}' is not an Ansiblectl workspace.")
        try:
            data = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise WorkspaceValidationError(
                f"Workspace metadata at '{metadata_path}' is unreadable. "
                "Restore a valid metadata file or initialise a new workspace."
            ) from error
        return _workspace_from_data(root, metadata_path, data)

    def initialize(self, root: Path) -> Workspace:
        """Create a workspace once, or return the existing valid workspace unchanged."""

        metadata_path = _metadata_path(root)
        if metadata_path.exists():
            return self.load(root)
        metadata_directory = metadata_path.parent
        if metadata_directory.exists():
            raise WorkspaceValidationError(
                f"'{metadata_directory}' already exists without workspace metadata. "
                "Restore workspace.json or choose an empty directory."
            )
        try:
            metadata_directory.mkdir(parents=True, exist_ok=False)
            _atomic_write(metadata_path, {"schema_version": WORKSPACE_SCHEMA_VERSION})
        except OSError as error:
            raise WorkspaceValidationError(
                f"Could not initialise workspace at '{root}'. Check path permissions and retry."
            ) from error
        return Workspace(
            root=root, metadata_path=metadata_path, schema_version=WORKSPACE_SCHEMA_VERSION
        )


def _metadata_path(root: Path) -> Path:
    metadata_path = root / WORKSPACE_DIRECTORY / WORKSPACE_METADATA_FILENAME
    if not metadata_path.is_relative_to(root):
        raise WorkspaceValidationError("Workspace metadata must remain within its workspace root.")
    return metadata_path


def _workspace_from_data(root: Path, metadata_path: Path, data: Any) -> Workspace:
    if not isinstance(data, dict) or set(data) != {"schema_version"}:
        raise WorkspaceValidationError(
            f"Workspace metadata at '{metadata_path}' has an invalid schema. "
            "Restore the versioned metadata format."
        )
    version = data["schema_version"]
    if version != WORKSPACE_SCHEMA_VERSION:
        raise WorkspaceValidationError(
            f"Workspace metadata schema {version!r} is unsupported. "
            f"Expected schema {WORKSPACE_SCHEMA_VERSION}."
        )
    return Workspace(root=root, metadata_path=metadata_path, schema_version=version)


def _atomic_write(path: Path, data: dict[str, int]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=".workspace-", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(data, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(path)
    except OSError:
        temporary_path.unlink(missing_ok=True)
        raise

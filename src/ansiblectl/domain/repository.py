"""Repository contracts independent of Git."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ansiblectl.domain.errors import DomainError


class RepositoryError(DomainError):
    """Base error for safe, actionable repository failures."""


class DirtyWorktreeError(RepositoryError):
    """Raised when an operation would overwrite uncommitted user work."""


@dataclass(frozen=True)
class RepositoryRequest:
    workspace_root: Path
    repository_path: Path
    revision: str

    def __post_init__(self) -> None:
        if not self.workspace_root.is_absolute() or not self.repository_path.is_absolute():
            raise RepositoryError(
                "Repository and workspace paths must be absolute validated paths."
            )
        if not self.repository_path.is_relative_to(self.workspace_root):
            raise RepositoryError("Repository path must remain inside the selected workspace.")
        if not self.revision.strip():
            raise RepositoryError("Repository revision must be explicit and non-empty.")


@dataclass(frozen=True)
class RepositoryResult:
    repository_path: Path
    revision: str
    dirty: bool


class RepositoryPort(Protocol):
    def inspect(self, request: RepositoryRequest) -> RepositoryResult:
        """Inspect repository state without mutation."""

    def sync(self, request: RepositoryRequest) -> RepositoryResult:
        """Synchronise an already validated clean repository to its revision."""


def require_clean_worktree(result: RepositoryResult) -> RepositoryResult:
    if result.dirty:
        raise DirtyWorktreeError(
            "Repository has uncommitted changes. Commit or stash them before synchronising."
        )
    return result

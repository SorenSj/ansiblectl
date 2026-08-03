"""Repository orchestration tests."""

from dataclasses import dataclass
from pathlib import Path

import pytest

from ansiblectl.application.repository import RepositoryService
from ansiblectl.domain.repository import (
    DirtyWorktreeError,
    RepositoryRequest,
    RepositoryResult,
    RevisionMismatchError,
)


@dataclass(frozen=True)
class FakeRepositoryPort:
    result: RepositoryResult

    def inspect(self, request: RepositoryRequest) -> RepositoryResult:
        return self.result

    def sync(self, request: RepositoryRequest) -> RepositoryResult:
        return RepositoryResult(request.repository_path, request.revision, False)


def test_dirty_worktree_is_not_overwritten(tmp_path: Path) -> None:
    request = RepositoryRequest(tmp_path, tmp_path / "repo", "main")
    result = RepositoryResult(request.repository_path, "main", True)

    with pytest.raises(DirtyWorktreeError, match="Commit or stash"):
        RepositoryService(FakeRepositoryPort(result)).inspect_for_sync(request)


def test_clean_worktree_is_inspected_before_sync(tmp_path: Path) -> None:
    request = RepositoryRequest(tmp_path, tmp_path / "repo", "main")
    result = RepositoryResult(request.repository_path, "main", False)
    assert RepositoryService(FakeRepositoryPort(result)).sync(request).revision == "main"


def test_execution_requires_requested_revision_at_head(tmp_path: Path) -> None:
    request = RepositoryRequest(tmp_path, tmp_path / "repo", "main")
    matching = RepositoryResult(request.repository_path, "main", False, "abc", "abc")
    mismatch = RepositoryResult(request.repository_path, "main", False, "abc", "def")

    service = RepositoryService(FakeRepositoryPort(matching))
    assert service.inspect_for_execution(request) == matching
    with pytest.raises(RevisionMismatchError, match="not checked out"):
        RepositoryService(FakeRepositoryPort(mismatch)).inspect_for_execution(request)

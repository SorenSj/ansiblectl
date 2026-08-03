"""Repository orchestration tests."""

from dataclasses import dataclass
from pathlib import Path

import pytest

from ansiblectl.application.repository import RepositoryService
from ansiblectl.domain.repository import DirtyWorktreeError, RepositoryRequest, RepositoryResult


@dataclass(frozen=True)
class FakeRepositoryPort:
    result: RepositoryResult

    def inspect(self, request: RepositoryRequest) -> RepositoryResult:
        return self.result


def test_dirty_worktree_is_not_overwritten(tmp_path: Path) -> None:
    request = RepositoryRequest(tmp_path, tmp_path / "repo", "main")
    result = RepositoryResult(request.repository_path, "main", True)

    with pytest.raises(DirtyWorktreeError, match="Commit or stash"):
        RepositoryService(FakeRepositoryPort(result)).inspect_for_sync(request)

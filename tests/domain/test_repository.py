"""Repository boundary tests."""

from pathlib import Path

import pytest

from ansiblectl.domain.repository import RepositoryError, RepositoryRequest


def test_repository_path_cannot_escape_workspace(tmp_path: Path) -> None:
    with pytest.raises(RepositoryError, match="inside the selected workspace"):
        RepositoryRequest(tmp_path, tmp_path.parent, "main")

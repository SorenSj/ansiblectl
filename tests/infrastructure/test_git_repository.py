"""Git adapter contract tests."""

import subprocess
from pathlib import Path

import pytest

from ansiblectl.domain.repository import RepositoryError, RepositoryRequest
from ansiblectl.infrastructure.git_repository import GitRepositoryAdapter


def test_adapter_uses_fixed_credential_free_git_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess([], 0, stdout=" M README.md\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    request = RepositoryRequest(tmp_path, tmp_path / "repo", "main")

    result = GitRepositoryAdapter().inspect(request)

    assert result.dirty is True
    assert captured["args"] == (("git", "status", "--porcelain"),)
    assert captured["kwargs"] == {
        "cwd": request.repository_path,
        "capture_output": True,
        "check": True,
        "shell": False,
        "text": True,
    }


def test_adapter_returns_actionable_error_when_git_inspection_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError("not available")

    monkeypatch.setattr(subprocess, "run", broken)

    with pytest.raises(RepositoryError, match="Verify it is a Git repository"):
        GitRepositoryAdapter().inspect(RepositoryRequest(tmp_path, tmp_path / "repo", "main"))

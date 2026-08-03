"""Git adapter contract tests."""

import subprocess
from pathlib import Path

import pytest

from ansiblectl.domain.repository import RepositoryError, RepositoryRequest
from ansiblectl.infrastructure.git_repository import GitRepositoryAdapter


def test_adapter_uses_fixed_credential_free_git_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[object, ...]] = []

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        argv = args[0]
        assert isinstance(argv, tuple)
        stdout = " M README.md\n" if argv[1] == "status" else "abc123\n"
        return subprocess.CompletedProcess([], 0, stdout=stdout)

    monkeypatch.setattr(subprocess, "run", fake_run)
    request = RepositoryRequest(tmp_path, tmp_path / "repo", "main")

    result = GitRepositoryAdapter().inspect(request)

    assert result.dirty is True
    assert result.resolved_revision == "abc123"
    assert result.head_revision == "abc123"
    assert calls == [
        (
            (
                "git",
                "status",
                "--porcelain",
                "--untracked-files=all",
                "--",
                ".",
                ":(exclude).ansiblectl",
            ),
        ),
        (("git", "rev-parse", "--verify", "main^{commit}"),),
        (("git", "rev-parse", "--verify", "HEAD"),),
    ]


def test_adapter_returns_actionable_error_when_git_inspection_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError("not available")

    monkeypatch.setattr(subprocess, "run", broken)

    with pytest.raises(RepositoryError, match="Verify it is a Git repository"):
        GitRepositoryAdapter().inspect(RepositoryRequest(tmp_path, tmp_path / "repo", "main"))


def test_sync_uses_fixed_non_credential_bearing_argument_vectors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[object, ...]] = []

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess([], 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    request = RepositoryRequest(tmp_path, tmp_path / "repo", "release-1")
    assert GitRepositoryAdapter().sync(request).revision == "release-1"
    assert calls == [
        (("git", "fetch", "--prune"),),
        (("git", "checkout", "--detach", "release-1"),),
    ]

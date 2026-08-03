"""Read-only Git repository adapter with no credential-bearing arguments."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from ansiblectl.domain.repository import RepositoryError, RepositoryRequest, RepositoryResult


@dataclass(frozen=True)
class GitRepositoryAdapter:
    def inspect(self, request: RepositoryRequest) -> RepositoryResult:
        try:
            status = subprocess.run(
                ("git", "status", "--porcelain"),
                cwd=request.repository_path,
                capture_output=True,
                check=True,
                shell=False,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise RepositoryError(
                f"Cannot inspect repository at '{request.repository_path}'. "
                "Verify it is a Git repository."
            ) from error
        return RepositoryResult(
            request.repository_path, request.revision, bool(status.stdout.strip())
        )

    def sync(self, request: RepositoryRequest) -> RepositoryResult:
        try:
            subprocess.run(
                ("git", "fetch", "--prune"),
                cwd=request.repository_path,
                capture_output=True,
                check=True,
                shell=False,
                text=True,
            )
            subprocess.run(
                ("git", "checkout", "--detach", request.revision),
                cwd=request.repository_path,
                capture_output=True,
                check=True,
                shell=False,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise RepositoryError(
                f"Cannot synchronise repository at '{request.repository_path}' "
                f"to '{request.revision}'. "
                "Verify revision and authentication policy."
            ) from error
        return RepositoryResult(request.repository_path, request.revision, False)

"""Repository inspection use case."""

from dataclasses import dataclass

from ansiblectl.domain.repository import (
    RepositoryPort,
    RepositoryRequest,
    RepositoryResult,
    require_checked_out_revision,
    require_clean_worktree,
)


@dataclass(frozen=True)
class RepositoryService:
    port: RepositoryPort

    def inspect(self, request: RepositoryRequest) -> RepositoryResult:
        return self.port.inspect(request)

    def inspect_for_sync(self, request: RepositoryRequest) -> RepositoryResult:
        return require_clean_worktree(self.port.inspect(request))

    def sync(self, request: RepositoryRequest) -> RepositoryResult:
        self.inspect_for_sync(request)
        self.port.sync(request)
        return require_checked_out_revision(self.port.inspect(request))

    def inspect_for_execution(self, request: RepositoryRequest) -> RepositoryResult:
        return require_checked_out_revision(self.port.inspect(request))

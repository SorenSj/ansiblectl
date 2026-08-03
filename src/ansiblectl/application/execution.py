"""Execution use case."""

from dataclasses import dataclass

from ansiblectl.domain.execution import ExecutionPort, ExecutionRequest, ExecutionResult


@dataclass(frozen=True)
class ExecutionService:
    """Submit a prepared request through an explicit execution port."""

    port: ExecutionPort

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute the prepared request without adapter-specific logic."""

        return self.port.execute(request)

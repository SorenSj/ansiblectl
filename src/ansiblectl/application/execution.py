"""Execution use case."""

from dataclasses import dataclass

from ansiblectl.domain.execution import ExecutionPort, ExecutionRequest, ExecutionResult
from ansiblectl.domain.policy import (
    EnforcementMode,
    EvaluationRequest,
    Policy,
    PolicyReport,
    evaluate,
)


@dataclass(frozen=True)
class ExecutionService:
    """Submit a prepared request through an explicit execution port."""

    port: ExecutionPort

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute the prepared request without adapter-specific logic."""

        return self.port.execute(request)


@dataclass(frozen=True)
class GovernedExecutionResult:
    """The policy decision and, only when allowed, the execution outcome."""

    report: PolicyReport
    execution: ExecutionResult | None


@dataclass(frozen=True)
class GovernedExecutionService:
    """Apply deterministic policy enforcement before an execution port is reached."""

    port: ExecutionPort
    policies: list[Policy]

    def execute(
        self,
        request: ExecutionRequest,
        evaluation_request: EvaluationRequest,
        mode: EnforcementMode,
    ) -> GovernedExecutionResult:
        report = evaluate(self.policies, evaluation_request, mode)
        if not report.allowed:
            return GovernedExecutionResult(report, None)
        return GovernedExecutionResult(report, self.port.execute(request))

"""Execution use case."""

from dataclasses import dataclass

from ansiblectl.domain.events import Event, EventBus
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
    events: EventBus | None = None

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute the prepared request without adapter-specific logic."""

        result = self.port.execute(request)
        if self.events is not None:
            self.events.publish(
                Event(
                    "execution.completed",
                    {
                        "execution_id": result.execution_id,
                        "status": result.status,
                        "exit_code": result.exit_code,
                        "elapsed_seconds": result.elapsed_seconds,
                        "stdout_reference": result.stdout_reference,
                        "stderr_reference": result.stderr_reference,
                        "diagnostic": result.diagnostic,
                        "targeting": {
                            "limit": request.targeting.limit,
                            "tags": list(request.targeting.tags),
                            "skip_tags": list(request.targeting.skip_tags),
                        },
                        "mode": request.mode,
                        "requested_revision": (
                            None
                            if request.selected_playbook is None
                            else request.selected_playbook.revision
                        ),
                        "resolved_revision": request.resolved_revision,
                        "inventory_digest": request.inventory_digest,
                        "playbook_digest": request.playbook_digest,
                        "playbook_path": request.playbook_path,
                    },
                )
            )
        return result


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
    events: EventBus | None = None

    def execute(
        self,
        request: ExecutionRequest,
        evaluation_request: EvaluationRequest,
        mode: EnforcementMode,
    ) -> GovernedExecutionResult:
        report = evaluate(self.policies, evaluation_request, mode)
        if not report.allowed:
            return GovernedExecutionResult(report, None)
        execution = ExecutionService(self.port, self.events).execute(request)
        return GovernedExecutionResult(report, execution)

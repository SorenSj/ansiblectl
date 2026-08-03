"""Policy evaluation use case."""

from dataclasses import dataclass

from ansiblectl.domain.policy import (
    EnforcementMode,
    EvaluationRequest,
    Policy,
    PolicyReport,
    evaluate,
)


@dataclass(frozen=True)
class PolicyService:
    policies: list[Policy]

    def evaluate(self, request: EvaluationRequest, mode: EnforcementMode) -> PolicyReport:
        return evaluate(self.policies, request, mode)

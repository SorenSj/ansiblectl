"""Execution use-case tests with a fake port."""

from dataclasses import dataclass
from pathlib import Path

from ansiblectl.application.execution import ExecutionService, GovernedExecutionService
from ansiblectl.domain.events import Event, EventBus
from ansiblectl.domain.execution import (
    ExecutionMode,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    ExecutionTargeting,
)
from ansiblectl.domain.policy import EnforcementMode, EvaluationRequest, PolicyFinding


@dataclass(frozen=True)
class FakeExecutionPort:
    result: ExecutionResult

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        assert request.argv == ("ansible-playbook", "site.yml")
        return self.result


def test_service_submits_request_to_fake_port(tmp_path: Path) -> None:
    request = ExecutionRequest(("ansible-playbook", "site.yml"), tmp_path, {})
    result = ExecutionResult(request.execution_id, ExecutionStatus.COMPLETED, 0, 0.1)

    assert ExecutionService(FakeExecutionPort(result)).execute(request) == result


@dataclass
class RecordingExecutionPort:
    result: ExecutionResult
    calls: int = 0

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.calls += 1
        return self.result


@dataclass(frozen=True)
class DenyingPolicy:
    def evaluate(self, request: EvaluationRequest) -> tuple[PolicyFinding, ...]:
        return (PolicyFinding("POL-001", "high", "Blocked", request.location),)


def test_deny_policy_prevents_execution_port_invocation(tmp_path: Path) -> None:
    request = ExecutionRequest(("ansible-playbook", "site.yml"), tmp_path, {})
    port = RecordingExecutionPort(
        ExecutionResult(request.execution_id, ExecutionStatus.COMPLETED, 0, 0.1)
    )

    result = GovernedExecutionService(port, [DenyingPolicy()]).execute(
        request, EvaluationRequest("execute", "site.yml"), EnforcementMode.DENY
    )

    assert result.execution is None
    assert result.report.allowed is False
    assert port.calls == 0


def test_execution_event_is_published_after_a_completed_port_call(tmp_path: Path) -> None:
    request = ExecutionRequest(
        ("ansible-playbook", "site.yml"),
        tmp_path,
        {},
        targeting=ExecutionTargeting("web", ("deploy",), ("slow",)),
        mode=ExecutionMode.APPLY,
        resolved_revision="abc123",
    )
    result = ExecutionResult(request.execution_id, ExecutionStatus.COMPLETED, 0, 0.1)
    delivered: list[Event] = []

    assert (
        ExecutionService(FakeExecutionPort(result), EventBus([delivered.append])).execute(request)
        == result
    )
    assert delivered == [
        Event(
            "execution.completed",
            {
                "execution_id": request.execution_id,
                "status": ExecutionStatus.COMPLETED,
                "exit_code": 0,
                "elapsed_seconds": 0.1,
                "stdout_reference": None,
                "stderr_reference": None,
                "diagnostic": None,
                "targeting": {"limit": "web", "tags": ["deploy"], "skip_tags": ["slow"]},
                "mode": ExecutionMode.APPLY,
                "requested_revision": None,
                "resolved_revision": "abc123",
            },
        )
    ]

"""Execution use-case tests with a fake port."""

from dataclasses import dataclass
from pathlib import Path

from ansiblectl.application.execution import ExecutionService
from ansiblectl.domain.execution import ExecutionRequest, ExecutionResult, ExecutionStatus


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

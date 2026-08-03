"""Prepared run use-case tests."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import yaml

from ansiblectl.application.execution import ExecutionService
from ansiblectl.application.inventory import InventoryService
from ansiblectl.application.policy import PolicyService
from ansiblectl.application.run import RunService
from ansiblectl.domain.execution import ExecutionRequest, ExecutionResult, ExecutionStatus
from ansiblectl.domain.inventory import Host, InventoryFragment
from ansiblectl.domain.policy import EnforcementMode, EvaluationRequest, PolicyFinding


class FakeInventoryProvider:
    def load(self) -> InventoryFragment:
        host = Host("web-1", "192.0.2.10", {"ansible_port": 22}, "fixture")
        return InventoryFragment("fixture", {"web-1": host}, {"web": ("web-1",)})


class RecordingExecutionPort:
    request: ExecutionRequest | None = None
    inventory: dict[str, object] | None = None

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.request = request
        inventory_path = Path(request.argv[2])
        self.inventory = yaml.safe_load(inventory_path.read_text(encoding="utf-8"))
        return ExecutionResult(request.execution_id, ExecutionStatus.COMPLETED, 0, 0.1)


@contextmanager
def fake_materializer(inventory: object) -> Iterator[Path]:
    path = Path("/tmp/generated-inventory.yml")
    path.write_text(yaml.safe_dump(inventory), encoding="utf-8")
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


def test_run_prepares_check_mode_request_from_validated_inputs(tmp_path: Path) -> None:
    playbook = tmp_path / "playbooks/site.yml"
    playbook.parent.mkdir()
    playbook.write_text("---\n", encoding="utf-8")
    port = RecordingExecutionPort()
    service = RunService(
        InventoryService([FakeInventoryProvider()]),
        ExecutionService(port),
        PolicyService([]),
        fake_materializer,
    )

    result = service.run_check(
        tmp_path,
        Path("playbooks/site.yml"),
        "main",
        {"PATH": "/bin"},
        30,
        EnforcementMode.DENY,
    )

    assert result.execution is not None
    assert result.execution.status is ExecutionStatus.COMPLETED
    assert port.request is not None
    assert port.request.argv[:2] == ("ansible-playbook", "--inventory")
    assert "--check" in port.request.argv
    assert port.request.selected_playbook is not None
    assert port.request.selected_playbook.revision == "main"
    assert port.inventory == {
        "groups": {"web": ["web-1"]},
        "hosts": {"web-1": {"address": "192.0.2.10", "variables": {"ansible_port": 22}}},
    }


class DenyingPolicy:
    def evaluate(self, request: EvaluationRequest) -> tuple[PolicyFinding, ...]:
        return (PolicyFinding("RUN-001", "high", "Denied", request.location),)


def test_deny_policy_prevents_materialization_and_execution(tmp_path: Path) -> None:
    playbook = tmp_path / "site.yml"
    playbook.write_text("---\n", encoding="utf-8")
    port = RecordingExecutionPort()
    materialized = False

    @contextmanager
    def recording_materializer(inventory: object) -> Iterator[Path]:
        nonlocal materialized
        materialized = True
        yield tmp_path / "unused.yml"

    service = RunService(
        InventoryService([FakeInventoryProvider()]),
        ExecutionService(port),
        PolicyService([DenyingPolicy()]),
        recording_materializer,
    )

    result = service.run_check(tmp_path, Path("site.yml"), "main", {}, 30, EnforcementMode.DENY)

    assert result.report.allowed is False
    assert result.execution is None
    assert materialized is False
    assert port.request is None

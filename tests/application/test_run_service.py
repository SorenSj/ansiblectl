"""Prepared run use-case tests."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
import yaml

from ansiblectl.application.configuration import ConfigurationService
from ansiblectl.application.execution import ExecutionService
from ansiblectl.application.inventory import InventoryService
from ansiblectl.application.policy import PolicyService
from ansiblectl.application.repository import RepositoryService
from ansiblectl.application.run import RunService
from ansiblectl.application.standard_policies import ApplyRequiresLimitPolicy
from ansiblectl.domain.configuration import ConfigurationSource
from ansiblectl.domain.errors import ConfigurationError, ExecutionError
from ansiblectl.domain.execution import (
    ExecutionMode,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    ExecutionTargeting,
)
from ansiblectl.domain.inventory import Host, InventoryFragment
from ansiblectl.domain.policy import EnforcementMode, EvaluationRequest, PolicyFinding
from ansiblectl.domain.repository import RepositoryRequest, RepositoryResult


class FakeInventoryProvider:
    def load(self) -> InventoryFragment:
        host = Host("web-1", "192.0.2.10", {"ansible_port": 22}, "fixture")
        return InventoryFragment("fixture", {"web-1": host}, {"web": ("web-1",)})


class FailingConfigurationProvider:
    def sources(self) -> list[ConfigurationSource]:
        raise ConfigurationError("Configuration preflight failed safely.")


class RecordingExecutionPort:
    request: ExecutionRequest | None = None
    inventory: dict[str, object] | None = None

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.request = request
        inventory_path = Path(request.argv[request.argv.index("--inventory") + 1])
        self.inventory = yaml.safe_load(inventory_path.read_text(encoding="utf-8"))
        return ExecutionResult(request.execution_id, ExecutionStatus.COMPLETED, 0, 0.1)


class RecordingPolicy:
    requests: list[EvaluationRequest]

    def __init__(self) -> None:
        self.requests = []

    def evaluate(self, request: EvaluationRequest) -> tuple[PolicyFinding, ...]:
        self.requests.append(request)
        return ()


class FakeRunRepositoryPort:
    def __init__(self, result: RepositoryResult) -> None:
        self.result = result

    def inspect(self, request: RepositoryRequest) -> RepositoryResult:
        return self.result

    def sync(self, request: RepositoryRequest) -> RepositoryResult:
        return self.result


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
        ExecutionTargeting("web:&staging", ("deploy", "config"), ("slow",)),
        3,
        True,
    )

    assert result.execution is not None
    assert result.execution.status is ExecutionStatus.COMPLETED
    assert port.request is not None
    assert port.request.argv[:3] == ("ansible-playbook", "-vvv", "--inventory")
    assert "--check" in port.request.argv
    assert port.request.argv[4:] == (
        "--check",
        "--diff",
        "--limit",
        "web:&staging",
        "--tags",
        "deploy,config",
        "--skip-tags",
        "slow",
        str(playbook),
    )
    assert port.request.targeting.limit == "web:&staging"
    assert port.request.inventory_digest is not None
    assert port.request.inventory_digest.startswith("sha256:")
    assert port.request.playbook_digest is not None
    assert port.request.playbook_digest.startswith("sha256:")
    assert port.request.playbook_path == "playbooks/site.yml"
    assert port.request.verbosity == 3
    assert port.request.diff is True
    assert port.request.selected_playbook is not None
    assert port.request.selected_playbook.revision == "main"
    assert port.inventory == {
        "groups": {"web": ["web-1"]},
        "hosts": {"web-1": {"address": "192.0.2.10", "variables": {"ansible_port": 22}}},
    }


def test_run_rejects_negative_verbosity_before_input_resolution(tmp_path: Path) -> None:
    service = RunService(
        InventoryService([FakeInventoryProvider()]),
        ExecutionService(RecordingExecutionPort()),
        PolicyService([]),
        fake_materializer,
    )

    with pytest.raises(ExecutionError, match="verbosity"):
        service.run_check(
            tmp_path,
            Path("missing.yml"),
            "main",
            {},
            30,
            EnforcementMode.DENY,
            verbosity=-1,
        )


def test_run_validates_configuration_before_playbook_and_inventory(tmp_path: Path) -> None:
    port = RecordingExecutionPort()
    environment_prepared = False

    def prepare_environment() -> dict[str, str]:
        nonlocal environment_prepared
        environment_prepared = True
        return {}

    service = RunService(
        InventoryService([FakeInventoryProvider()]),
        ExecutionService(port),
        PolicyService([]),
        fake_materializer,
        configuration=ConfigurationService(FailingConfigurationProvider()),
    )

    with pytest.raises(ConfigurationError, match="preflight failed"):
        service.run_check(
            tmp_path,
            Path("missing-playbook.yml"),
            "main",
            prepare_environment,
            30,
            EnforcementMode.DENY,
        )

    assert port.request is None
    assert environment_prepared is False


def test_apply_requires_confirmation_before_execution(tmp_path: Path) -> None:
    playbook = tmp_path / "site.yml"
    playbook.write_text("---\n", encoding="utf-8")
    port = RecordingExecutionPort()
    policy = RecordingPolicy()
    repository_result = RepositoryResult(tmp_path, "main", False, "abc", "abc")
    service = RunService(
        InventoryService([FakeInventoryProvider()]),
        ExecutionService(port),
        PolicyService([policy]),
        fake_materializer,
        RepositoryService(FakeRunRepositoryPort(repository_result)),
    )

    with pytest.raises(ExecutionError, match="explicit confirmation"):
        service.run_apply(tmp_path, Path("site.yml"), "main", {}, 30, EnforcementMode.DENY, False)
    assert port.request is None
    assert policy.requests == []


def test_confirmed_apply_omits_check_argument(tmp_path: Path) -> None:
    playbook = tmp_path / "site.yml"
    playbook.write_text("---\n", encoding="utf-8")
    port = RecordingExecutionPort()
    policy = RecordingPolicy()
    repository_result = RepositoryResult(tmp_path, "main", False, "abc", "abc")
    service = RunService(
        InventoryService([FakeInventoryProvider()]),
        ExecutionService(port),
        PolicyService([policy]),
        fake_materializer,
        RepositoryService(FakeRunRepositoryPort(repository_result)),
    )

    result = service.run_apply(
        tmp_path, Path("site.yml"), "main", {}, 30, EnforcementMode.DENY, True
    )

    assert result.execution is not None
    request = port.request
    assert request is not None
    assert "--check" not in request.argv
    assert request.mode is ExecutionMode.APPLY
    assert request.resolved_revision == "abc"
    assert policy.requests[0].operation == "run.apply"
    assert policy.requests[0].attributes["repository_dirty"] is False
    assert policy.requests[0].attributes["resolved_revision"] == "abc"
    assert str(policy.requests[0].attributes["inventory_digest"]).startswith("sha256:")
    assert str(policy.requests[0].attributes["playbook_digest"]).startswith("sha256:")
    assert policy.requests[0].attributes["verbosity"] == 0
    assert policy.requests[0].attributes["diff"] is False


def test_default_apply_limit_policy_blocks_before_materialization(tmp_path: Path) -> None:
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
        PolicyService([ApplyRequiresLimitPolicy()]),
        recording_materializer,
    )

    result = service.run_apply(
        tmp_path, Path("site.yml"), "main", {}, 30, EnforcementMode.DENY, True
    )

    assert result.execution is None
    assert result.report.findings[0].rule_id == "ANSIBLECTL-APPLY-001"
    assert materialized is False
    assert port.request is None


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

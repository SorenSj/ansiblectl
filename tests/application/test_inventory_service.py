"""Inventory use-case tests."""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from ansiblectl.application.execution import ExecutionService
from ansiblectl.application.inventory import InventoryService, InventoryValidationService
from ansiblectl.domain.execution import ExecutionRequest, ExecutionResult, ExecutionStatus
from ansiblectl.domain.inventory import Host, InventoryFragment


@dataclass(frozen=True)
class FakeProvider:
    def load(self) -> InventoryFragment:
        return InventoryFragment(
            "fake", {"localhost": Host("localhost", "127.0.0.1", {}, "fake")}, {}
        )


def test_service_uses_fake_provider() -> None:
    assert InventoryService([FakeProvider()]).resolve().hosts["localhost"].address == "127.0.0.1"


@dataclass
class RecordingPort:
    request: ExecutionRequest | None = None

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.request = request
        return ExecutionResult(
            request.execution_id,
            ExecutionStatus.COMPLETED,
            0,
            0.1,
            inventory_digest=request.inventory_digest,
            operation=request.operation,
        )


def test_validation_materializes_canonical_inventory_and_invokes_ansible(tmp_path: Path) -> None:
    materialized: list[Mapping[str, object]] = []

    @contextmanager
    def materialize(inventory: Mapping[str, object]) -> Iterator[Path]:
        materialized.append(inventory)
        yield tmp_path / ".ansiblectl/tmp/inventory.yml"

    port = RecordingPort()
    result = InventoryValidationService(
        InventoryService([FakeProvider()]), ExecutionService(port), materialize
    ).validate(tmp_path, {"PATH": "/usr/bin"}, 15.0)

    assert materialized == [
        {"hosts": {"localhost": {"address": "127.0.0.1", "variables": {}}}, "groups": {}}
    ]
    assert port.request is not None
    assert port.request.argv == (
        "ansible-inventory",
        "--inventory",
        str(tmp_path / ".ansiblectl/tmp/inventory.yml"),
        "--list",
    )
    assert port.request.timeout_seconds == 15.0
    assert port.request.operation == "inventory.validate"
    assert result.execution.status is ExecutionStatus.COMPLETED
    assert result.digest == port.request.inventory_digest

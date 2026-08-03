"""Inventory resolution and Ansible validation use cases."""

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path

from ansiblectl.application.execution import ExecutionService
from ansiblectl.domain.execution import ExecutionRequest, ExecutionResult
from ansiblectl.domain.inventory import (
    InventoryProvider,
    ResolvedInventory,
    canonical_inventory_digest,
    resolve_inventory,
)

InventoryMaterializer = Callable[[Mapping[str, object]], AbstractContextManager[Path]]


@dataclass(frozen=True)
class InventoryService:
    providers: list[InventoryProvider]

    def resolve(self) -> ResolvedInventory:
        return resolve_inventory(self.providers)


@dataclass(frozen=True)
class InventoryValidationResult:
    """Safe validation evidence without rendered inventory content."""

    digest: str
    execution: ExecutionResult


@dataclass(frozen=True)
class InventoryValidationService:
    """Validate the generated native inventory through Ansible itself."""

    inventory: InventoryService
    execution: ExecutionService
    materialize_inventory: InventoryMaterializer

    def validate(
        self,
        workspace_root: Path,
        environment: Mapping[str, str],
        timeout_seconds: float,
    ) -> InventoryValidationResult:
        canonical = self.inventory.resolve().canonical()
        digest = canonical_inventory_digest(canonical)
        with self.materialize_inventory(canonical) as inventory_path:
            result = self.execution.execute(
                ExecutionRequest(
                    ("ansible-inventory", "--inventory", str(inventory_path), "--list"),
                    workspace_root.resolve(),
                    environment,
                    timeout_seconds=timeout_seconds,
                    inventory_digest=digest,
                    operation="inventory.validate",
                )
            )
        return InventoryValidationResult(digest, result)

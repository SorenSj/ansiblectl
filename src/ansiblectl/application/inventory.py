"""Inventory resolution use case."""

from dataclasses import dataclass

from ansiblectl.domain.inventory import InventoryProvider, ResolvedInventory, resolve_inventory


@dataclass(frozen=True)
class InventoryService:
    providers: list[InventoryProvider]

    def resolve(self) -> ResolvedInventory:
        return resolve_inventory(self.providers)

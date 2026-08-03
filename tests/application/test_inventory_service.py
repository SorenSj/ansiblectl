"""Inventory use-case tests."""

from dataclasses import dataclass

from ansiblectl.application.inventory import InventoryService
from ansiblectl.domain.inventory import Host, InventoryFragment


@dataclass(frozen=True)
class FakeProvider:
    def load(self) -> InventoryFragment:
        return InventoryFragment(
            "fake", {"localhost": Host("localhost", "127.0.0.1", {}, "fake")}, {}
        )


def test_service_uses_fake_provider() -> None:
    assert InventoryService([FakeProvider()]).resolve().hosts["localhost"].address == "127.0.0.1"

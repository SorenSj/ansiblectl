"""Inventory merging and validation tests."""

from dataclasses import dataclass

import pytest

from ansiblectl.domain.inventory import (
    Host,
    InventoryError,
    InventoryFragment,
    canonical_inventory_digest,
    resolve_inventory,
)


@dataclass(frozen=True)
class FakeProvider:
    fragment: InventoryFragment

    def load(self) -> InventoryFragment:
        return self.fragment


def test_later_provider_overrides_host_and_records_provenance() -> None:
    low = InventoryFragment(
        "defaults", {"web": Host("web", "10.0.0.1", {}, "defaults")}, {"webservers": ("web",)}
    )
    high = InventoryFragment(
        "project", {"web": Host("web", "10.0.0.2", {}, "project")}, {"webservers": ("web",)}
    )

    resolved = resolve_inventory([FakeProvider(low), FakeProvider(high)])

    assert resolved.hosts["web"].address == "10.0.0.2"
    assert resolved.provenance["web"] == "project"
    assert "overrides defaults" in resolved.diagnostics[0]
    assert resolved.canonical()["groups"] == {"webservers": ["web"]}


def test_invalid_group_fails_before_execution() -> None:
    fragment = InventoryFragment("broken", {}, {"webservers": ("missing",)})

    with pytest.raises(InventoryError, match="Reference resolved host names"):
        resolve_inventory([FakeProvider(fragment)])


def test_canonical_inventory_digest_is_stable_and_content_sensitive() -> None:
    first = {"hosts": {"web": {"address": "192.0.2.1"}}, "groups": {"all": ["web"]}}
    reordered = {"groups": {"all": ["web"]}, "hosts": {"web": {"address": "192.0.2.1"}}}
    changed = {"groups": {"all": ["web"]}, "hosts": {"web": {"address": "192.0.2.2"}}}

    digest = canonical_inventory_digest(first)

    assert digest.startswith("sha256:")
    assert digest == canonical_inventory_digest(reordered)
    assert digest != canonical_inventory_digest(changed)

"""Ephemeral canonical inventory tests."""

from pathlib import Path

import pytest
import yaml

from ansiblectl.domain.inventory import InventoryError
from ansiblectl.infrastructure.generated_inventory import materialize_inventory


def test_materialized_inventory_is_private_ansible_yaml_and_removed() -> None:
    canonical = {
        "hosts": {"web-1": {"address": "192.0.2.10", "variables": {"ansible_port": 22}}},
        "groups": {"all": ["web-1"], "web": ["web-1"]},
    }

    with materialize_inventory(canonical) as path:
        generated = Path(path)
        assert generated.is_file()
        assert generated.stat().st_mode & 0o777 == 0o600
        assert yaml.safe_load(generated.read_text(encoding="utf-8")) == {
            "all": {
                "children": {"web": {"hosts": {"web-1": {}}}},
                "hosts": {"web-1": {"ansible_host": "192.0.2.10", "ansible_port": 22}},
            }
        }

    assert generated.exists() is False


def test_materializer_rejects_invalid_canonical_shape() -> None:
    with (
        pytest.raises(InventoryError, match="host and group mappings"),
        materialize_inventory({"hosts": []}),
    ):
        raise AssertionError("Invalid inventory must not be yielded.")

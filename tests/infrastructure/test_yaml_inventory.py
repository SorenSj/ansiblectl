"""Ansible YAML inventory provider tests."""

from pathlib import Path

import pytest

from ansiblectl.domain.inventory import InventoryError
from ansiblectl.infrastructure.yaml_inventory import YamlInventoryProvider


def test_provider_loads_nested_ansible_groups_with_provenance(tmp_path: Path) -> None:
    path = tmp_path / "hosts.yml"
    path.write_text(
        "all:\n"
        "  children:\n"
        "    web:\n"
        "      hosts:\n"
        "        web-1:\n"
        "          ansible_host: 192.0.2.10\n"
        "          ansible_port: 2222\n"
        "          role: frontend\n",
        encoding="utf-8",
    )

    fragment = YamlInventoryProvider(path).load()

    assert fragment.hosts["web-1"].address == "192.0.2.10"
    assert fragment.hosts["web-1"].variables == {"ansible_port": 2222, "role": "frontend"}
    assert fragment.groups == {"web": ("web-1",), "all": ("web-1",)}
    assert fragment.source == str(path)


def test_provider_rejects_invalid_host_address_with_source(tmp_path: Path) -> None:
    path = tmp_path / "hosts.yml"
    path.write_text("all:\n  hosts:\n    web-1:\n      ansible_host: [invalid]\n", encoding="utf-8")

    with pytest.raises(InventoryError, match=f"ansible_host.*web-1.*{path}"):
        YamlInventoryProvider(path).load()


def test_provider_reports_missing_all_mapping(tmp_path: Path) -> None:
    path = tmp_path / "hosts.yml"
    path.write_text("web: []\n", encoding="utf-8")

    with pytest.raises(InventoryError, match="must contain an 'all'"):
        YamlInventoryProvider(path).load()

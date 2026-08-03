"""Ephemeral materialisation of canonical inventory for Ansible execution."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

import yaml

from ansiblectl.domain.inventory import InventoryError


@contextmanager
def materialize_inventory(inventory: Mapping[str, object]) -> Iterator[Path]:
    """Yield a private YAML inventory file and remove it after execution."""

    descriptor, name = tempfile.mkstemp(prefix="ansiblectl-inventory-", suffix=".yaml")
    path = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            yaml.safe_dump(_ansible_inventory(inventory), stream, sort_keys=True)
        path.chmod(0o600)
        yield path
    finally:
        path.unlink(missing_ok=True)


def _ansible_inventory(inventory: Mapping[str, object]) -> dict[str, object]:
    """Transform the validated canonical mapping into native Ansible YAML inventory."""

    hosts = inventory.get("hosts")
    groups = inventory.get("groups")
    if not isinstance(hosts, Mapping) or not isinstance(groups, Mapping):
        raise InventoryError("Canonical inventory must contain host and group mappings.")
    ansible_hosts: dict[str, object] = {}
    for name, raw_host in hosts.items():
        if not isinstance(name, str) or not isinstance(raw_host, Mapping):
            raise InventoryError("Canonical inventory contains an invalid host entry.")
        address = raw_host.get("address")
        variables = raw_host.get("variables", {})
        if not isinstance(address, str) or not isinstance(variables, Mapping):
            raise InventoryError(f"Canonical host '{name}' has invalid execution data.")
        ansible_hosts[name] = {**dict(variables), "ansible_host": address}
    children: dict[str, object] = {}
    for name, members in groups.items():
        if name == "all":
            continue
        if (
            not isinstance(name, str)
            or not isinstance(members, list)
            or not all(isinstance(member, str) for member in members)
        ):
            raise InventoryError("Canonical inventory contains an invalid group entry.")
        children[name] = {"hosts": {member: {} for member in members}}
    all_group: dict[str, object] = {"hosts": ansible_hosts}
    if children:
        all_group["children"] = children
    return {"all": all_group}

"""Safe provider for a deterministic subset of Ansible YAML inventory."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from ansiblectl.domain.inventory import Host, InventoryError, InventoryFragment


@dataclass(frozen=True)
class YamlInventoryProvider:
    """Load hosts and nested groups without invoking plugin or inventory code."""

    path: Path

    def load(self) -> InventoryFragment:
        source = str(self.path)
        try:
            data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as error:
            raise InventoryError(
                f"Inventory at '{source}' cannot be parsed safely. Correct the YAML and retry."
            ) from error
        if not isinstance(data, Mapping) or not isinstance(data.get("all"), Mapping):
            raise InventoryError(f"Inventory at '{source}' must contain an 'all' YAML mapping.")

        hosts: dict[str, Host] = {}
        groups: dict[str, tuple[str, ...]] = {}
        self._load_group("all", data["all"], hosts, groups, source)
        return InventoryFragment(source, hosts, groups)

    def _load_group(
        self,
        name: str,
        node: object,
        hosts: dict[str, Host],
        groups: dict[str, tuple[str, ...]],
        source: str,
    ) -> tuple[str, ...]:
        if not isinstance(node, Mapping):
            raise InventoryError(f"Group '{name}' in {source} must be a YAML mapping.")
        members: list[str] = []
        host_values = node.get("hosts", {})
        if not isinstance(host_values, Mapping):
            raise InventoryError(f"Hosts for group '{name}' in {source} must be a mapping.")
        for host_name, raw_variables in host_values.items():
            host = self._load_host(host_name, raw_variables, source)
            existing = hosts.get(host.name)
            if existing is not None and existing != host:
                raise InventoryError(f"Host '{host.name}' has conflicting definitions in {source}.")
            hosts[host.name] = host
            members.append(host.name)

        children = node.get("children", {})
        if not isinstance(children, Mapping):
            raise InventoryError(f"Children for group '{name}' in {source} must be a mapping.")
        for child_name, child_node in children.items():
            if not isinstance(child_name, str) or not child_name:
                raise InventoryError(f"Group name in {source} must be a non-empty string.")
            members.extend(self._load_group(child_name, child_node, hosts, groups, source))
        groups[name] = tuple(dict.fromkeys(members))
        return groups[name]

    @staticmethod
    def _load_host(name: object, raw_variables: object, source: str) -> Host:
        if not isinstance(name, str) or not name:
            raise InventoryError(f"Host name in {source} must be a non-empty string.")
        if raw_variables is None:
            variables: dict[str, object] = {}
        elif isinstance(raw_variables, Mapping) and all(
            isinstance(key, str) for key in raw_variables
        ):
            variables = dict(raw_variables)
        else:
            raise InventoryError(f"Variables for host '{name}' in {source} must be a YAML mapping.")
        address = variables.pop("ansible_host", name)
        if not isinstance(address, str) or not address:
            raise InventoryError(
                f"Variable 'ansible_host' for host '{name}' in {source} must be a string."
            )
        return Host(name, address, variables, source)

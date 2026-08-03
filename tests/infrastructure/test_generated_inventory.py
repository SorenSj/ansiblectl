"""Ephemeral canonical inventory tests."""

from pathlib import Path

import yaml

from ansiblectl.infrastructure.generated_inventory import materialize_inventory


def test_materialized_inventory_is_private_canonical_and_removed() -> None:
    canonical = {"hosts": {"web-1": {"address": "192.0.2.10"}}, "groups": {}}

    with materialize_inventory(canonical) as path:
        generated = Path(path)
        assert generated.is_file()
        assert generated.stat().st_mode & 0o777 == 0o600
        assert yaml.safe_load(generated.read_text(encoding="utf-8")) == canonical

    assert generated.exists() is False

"""Ephemeral materialisation of canonical inventory for Ansible execution."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

import yaml


@contextmanager
def materialize_inventory(inventory: Mapping[str, object]) -> Iterator[Path]:
    """Yield a private YAML inventory file and remove it after execution."""

    descriptor, name = tempfile.mkstemp(prefix="ansiblectl-inventory-", suffix=".yaml")
    path = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            yaml.safe_dump(dict(inventory), stream, sort_keys=True)
        path.chmod(0o600)
        yield path
    finally:
        path.unlink(missing_ok=True)

"""Validate version, tag, and release-note agreement before artifact delivery."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path


def validate_release(root: Path, tag: str | None = None) -> str:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    version = project["version"]
    if not isinstance(version, str) or not version:
        raise ValueError("Project version must be a non-empty string.")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    if f"## [{version}] - " not in changelog:
        raise ValueError(f"CHANGELOG.md must contain dated release notes for {version}.")
    if tag is not None and tag != f"v{version}":
        raise ValueError(f"Release tag '{tag}' must match package version v{version}.")
    return version


def main() -> int:
    tag = os.environ.get("GITHUB_REF_NAME") if os.environ.get("GITHUB_REF_TYPE") == "tag" else None
    validate_release(Path("."), tag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

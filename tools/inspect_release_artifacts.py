"""Inspect built release artifacts and their provenance without installing them."""

from __future__ import annotations

import json
import subprocess
import tomllib
import zipfile
from email.parser import Parser
from hashlib import sha256
from pathlib import Path


def inspect_artifacts(root: Path, expected_revision: str) -> dict[str, str]:
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    wheels = tuple((root / "dist").glob("ansiblectl-*.whl"))
    source_archives = tuple((root / "dist").glob("ansiblectl-*.tar.gz"))
    if len(wheels) != 1 or len(source_archives) != 1:
        raise ValueError("Release inspection requires exactly one wheel and one source archive.")
    with zipfile.ZipFile(wheels[0]) as wheel:
        names = [name for name in wheel.namelist() if name.endswith(".dist-info/METADATA")]
        if len(names) != 1:
            raise ValueError("Wheel must contain exactly one METADATA file.")
        metadata = Parser().parsestr(wheel.read(names[0]).decode("utf-8"))
    if metadata["Name"] != "ansiblectl" or metadata["Version"] != version:
        raise ValueError("Wheel name and version must match authoritative package metadata.")
    provenance = json.loads((root / "dist/build-metadata.json").read_text(encoding="utf-8"))
    lock_digest = sha256((root / "uv.lock").read_bytes()).hexdigest()
    if provenance != {"dependency_lock_sha256": lock_digest, "source_revision": expected_revision}:
        raise ValueError("Build metadata must match the source revision and dependency lock.")
    return {
        "dependency_lock_sha256": lock_digest,
        "source_archive": source_archives[0].name,
        "source_revision": expected_revision,
        "version": version,
        "wheel": wheels[0].name,
    }


def main() -> int:
    revision = subprocess.run(
        ("git", "rev-parse", "HEAD"), capture_output=True, check=True, text=True
    ).stdout.strip()
    inspect_artifacts(Path("."), revision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

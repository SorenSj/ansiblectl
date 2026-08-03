"""Inspect built release artifacts and their provenance without installing them."""

from __future__ import annotations

import json
import subprocess
import tarfile
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
    expected_wheel = f"ansiblectl-{version}-py3-none-any.whl"
    expected_source = f"ansiblectl-{version}.tar.gz"
    if wheels[0].name != expected_wheel or source_archives[0].name != expected_source:
        raise ValueError("Release artifact names must match authoritative package metadata.")
    with zipfile.ZipFile(wheels[0]) as wheel:
        wheel_names = set(wheel.namelist())
        metadata_names = [name for name in wheel_names if name.endswith(".dist-info/METADATA")]
        if len(metadata_names) != 1:
            raise ValueError("Wheel must contain exactly one METADATA file.")
        metadata = Parser().parsestr(wheel.read(metadata_names[0]).decode("utf-8"))
    if metadata["Name"] != "ansiblectl" or metadata["Version"] != version:
        raise ValueError("Wheel name and version must match authoritative package metadata.")
    dist_info = f"ansiblectl-{version}.dist-info"
    required_wheel = {
        "ansiblectl/__init__.py",
        "ansiblectl/py.typed",
        f"{dist_info}/entry_points.txt",
    }
    if not required_wheel.issubset(wheel_names):
        raise ValueError("Wheel is missing the package, typing marker, or CLI entry point.")
    source_prefix = f"ansiblectl-{version}"
    with tarfile.open(source_archives[0], "r:gz") as source:
        source_names = {member.name for member in source.getmembers()}
    if any(Path(name).is_absolute() or ".." in Path(name).parts for name in source_names):
        raise ValueError("Source archive contains an unsafe member path.")
    required_source = {
        f"{source_prefix}/CHANGELOG.md",
        f"{source_prefix}/README.md",
        f"{source_prefix}/pyproject.toml",
        f"{source_prefix}/uv.lock",
        f"{source_prefix}/src/ansiblectl/__init__.py",
        f"{source_prefix}/src/ansiblectl/py.typed",
    }
    if not required_source.issubset(source_names):
        raise ValueError("Source archive is missing required package or release files.")
    provenance = json.loads((root / "dist/build-metadata.json").read_text(encoding="utf-8"))
    lock_digest = sha256((root / "uv.lock").read_bytes()).hexdigest()
    if provenance != {"dependency_lock_sha256": lock_digest, "source_revision": expected_revision}:
        raise ValueError("Build metadata must match the source revision and dependency lock.")
    return {
        "dependency_lock_sha256": lock_digest,
        "source_archive": expected_source,
        "source_revision": expected_revision,
        "version": version,
        "wheel": expected_wheel,
    }


def main() -> int:
    revision = subprocess.run(
        ("git", "rev-parse", "HEAD"), capture_output=True, check=True, text=True
    ).stdout.strip()
    inspect_artifacts(Path("."), revision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

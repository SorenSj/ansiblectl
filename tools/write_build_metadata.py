"""Write a traceability record next to built distribution artifacts."""

from __future__ import annotations

import json
import subprocess
from hashlib import sha256
from pathlib import Path


def write_metadata(root: Path, source_revision: str) -> Path:
    """Write deterministic build provenance beside the distribution artifacts."""

    lock_digest = sha256((root / "uv.lock").read_bytes()).hexdigest()
    metadata = {"source_revision": source_revision, "dependency_lock_sha256": lock_digest}
    path = root / "dist/build-metadata.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main() -> int:
    root = Path(".")
    revision = subprocess.run(
        ("git", "rev-parse", "HEAD"), capture_output=True, check=True, text=True
    ).stdout.strip()
    write_metadata(root, revision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

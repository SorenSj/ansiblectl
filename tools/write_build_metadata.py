"""Write a traceability record next to built distribution artifacts."""

from __future__ import annotations

import json
import subprocess
from hashlib import sha256
from pathlib import Path


def main() -> int:
    root = Path(".")
    revision = subprocess.run(
        ("git", "rev-parse", "HEAD"), capture_output=True, check=True, text=True
    ).stdout.strip()
    lock_digest = sha256((root / "uv.lock").read_bytes()).hexdigest()
    metadata = {"source_revision": revision, "dependency_lock_sha256": lock_digest}
    (root / "dist/build-metadata.json").write_text(json.dumps(metadata, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

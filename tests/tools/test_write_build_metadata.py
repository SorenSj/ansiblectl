"""Build provenance tests."""

import json
from hashlib import sha256
from pathlib import Path

from tools.write_build_metadata import write_metadata


def test_metadata_records_revision_and_locked_dependency_digest(tmp_path: Path) -> None:
    lock = tmp_path / "uv.lock"
    lock.write_bytes(b"locked dependencies")

    path = write_metadata(tmp_path, "abc123")

    assert path == tmp_path / "dist/build-metadata.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "dependency_lock_sha256": sha256(lock.read_bytes()).hexdigest(),
        "source_revision": "abc123",
    }

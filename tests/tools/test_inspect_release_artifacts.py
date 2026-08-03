"""Release artifact inspection tests."""

import json
import zipfile
from hashlib import sha256
from pathlib import Path

import pytest
from tools.inspect_release_artifacts import inspect_artifacts


def release_fixture(root: Path, revision: str = "a" * 40) -> None:
    (root / "pyproject.toml").write_text(
        '[project]\nname = "ansiblectl"\nversion = "1.2.3"\n', encoding="utf-8"
    )
    lock = root / "uv.lock"
    lock.write_bytes(b"locked")
    dist = root / "dist"
    dist.mkdir()
    with zipfile.ZipFile(dist / "ansiblectl-1.2.3-py3-none-any.whl", "w") as wheel:
        wheel.writestr(
            "ansiblectl-1.2.3.dist-info/METADATA",
            "Metadata-Version: 2.4\nName: ansiblectl\nVersion: 1.2.3\n",
        )
    (dist / "ansiblectl-1.2.3.tar.gz").write_bytes(b"source")
    (dist / "build-metadata.json").write_text(
        json.dumps(
            {
                "dependency_lock_sha256": sha256(lock.read_bytes()).hexdigest(),
                "source_revision": revision,
            }
        ),
        encoding="utf-8",
    )


def test_inspection_matches_wheel_version_revision_and_lock(tmp_path: Path) -> None:
    revision = "a" * 40
    release_fixture(tmp_path, revision)
    result = inspect_artifacts(tmp_path, revision)
    assert result["version"] == "1.2.3"
    assert result["source_revision"] == revision
    assert result["wheel"] == "ansiblectl-1.2.3-py3-none-any.whl"


def test_inspection_rejects_stale_provenance(tmp_path: Path) -> None:
    release_fixture(tmp_path)
    with pytest.raises(ValueError, match="source revision and dependency lock"):
        inspect_artifacts(tmp_path, "b" * 40)

"""Release validation tests."""

from pathlib import Path

import pytest
from tools.validate_release import validate_release


def write_release_files(root: Path, version: str = "1.2.3") -> None:
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "ansiblectl"\nversion = "{version}"\n', encoding="utf-8"
    )
    (root / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## [{version}] - 2026-08-03\n", encoding="utf-8"
    )


def test_release_version_tag_and_notes_must_agree(tmp_path: Path) -> None:
    write_release_files(tmp_path)

    assert validate_release(tmp_path, "v1.2.3") == "1.2.3"
    with pytest.raises(ValueError, match="must match package version"):
        validate_release(tmp_path, "v1.2.4")


def test_release_requires_dated_notes_for_package_version(tmp_path: Path) -> None:
    write_release_files(tmp_path)
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")

    with pytest.raises(ValueError, match="dated release notes"):
        validate_release(tmp_path)

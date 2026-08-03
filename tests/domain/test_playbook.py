"""Playbook boundary tests."""

from pathlib import Path

import pytest

from ansiblectl.domain.errors import ExecutionError
from ansiblectl.domain.execution import ExecutionRequest, ExecutionTargeting
from ansiblectl.domain.playbook import PlaybookError, select_playbook


def test_relative_playbook_resolves_inside_content_root(tmp_path: Path) -> None:
    path = tmp_path / "playbooks/site.yml"
    path.parent.mkdir()
    path.write_text("---\n")

    assert select_playbook(tmp_path, Path("playbooks/site.yml"), "main").path == path


def test_traversal_and_unsupported_types_are_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.yml"
    outside.write_text("---\n")
    with pytest.raises(PlaybookError, match="escapes"):
        select_playbook(tmp_path, Path("../outside.yml"), "main")
    invalid = tmp_path / "site.txt"
    invalid.write_text("x")
    with pytest.raises(PlaybookError, match="supported"):
        select_playbook(tmp_path, invalid, "main")


def test_execution_request_retains_canonical_playbook_and_revision(tmp_path: Path) -> None:
    path = tmp_path / "site.yml"
    path.write_text("---\n")
    selected = select_playbook(tmp_path, Path("site.yml"), "release-1")

    request = ExecutionRequest.for_playbook(("ansible-playbook", str(path)), tmp_path, {}, selected)

    assert request.selected_playbook == selected


def test_execution_targeting_rejects_empty_and_nul_values() -> None:
    with pytest.raises(ExecutionError, match="non-empty"):
        ExecutionTargeting(tags=("",))
    with pytest.raises(ExecutionError, match="no NUL"):
        ExecutionTargeting(limit="web\x00servers")

"""Workspace state-store tests."""

from pathlib import Path

import pytest

from ansiblectl.infrastructure.workspace_state import CacheEntry, StateError, WorkspaceStateStore


def test_atomic_state_round_trip_preserves_a_valid_record(tmp_path: Path) -> None:
    store = WorkspaceStateStore(tmp_path)
    entries = {"inventory": CacheEntry("git:main", "revision changes", {"hosts": 2})}
    store.write(entries)
    assert store.read() == entries


def test_corrupt_state_offers_recovery_path(tmp_path: Path) -> None:
    path = tmp_path / ".ansiblectl/state.json"
    path.parent.mkdir()
    path.write_text("broken")
    with pytest.raises(StateError, match="Remove .ansiblectl/state.json"):
        WorkspaceStateStore(tmp_path).read()

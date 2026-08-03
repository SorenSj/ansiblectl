"""Workspace state-store tests."""

from concurrent.futures import ThreadPoolExecutor
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


def test_unsupported_state_schema_offers_a_reset_path(tmp_path: Path) -> None:
    path = tmp_path / ".ansiblectl/state.json"
    path.parent.mkdir()
    path.write_text('{"schema_version": 999, "entries": {}}')

    with pytest.raises(StateError, match="schema is unsupported"):
        WorkspaceStateStore(tmp_path).read()


def test_invalid_cache_metadata_is_reported_as_corrupt_state(tmp_path: Path) -> None:
    path = tmp_path / ".ansiblectl/state.json"
    path.parent.mkdir()
    path.write_text(
        '{"schema_version":1,"entries":{"inventory":'
        '{"source_identity":{"secret":"value"},'
        '"invalidation_condition":"revision changes","value":{}}}}',
        encoding="utf-8",
    )

    with pytest.raises(StateError, match="State is corrupt"):
        WorkspaceStateStore(tmp_path).read()


def test_concurrent_atomic_updates_leave_a_valid_state_record(tmp_path: Path) -> None:
    store = WorkspaceStateStore(tmp_path)

    def write(value: int) -> None:
        store.write({"inventory": CacheEntry("git:main", "revision changes", {"hosts": value})})

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(write, (1, 2)))

    assert store.read()["inventory"].value["hosts"] in {1, 2}


def test_state_store_rejects_runtime_directory_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-state"
    outside.mkdir()
    (tmp_path / ".ansiblectl").symlink_to(outside, target_is_directory=True)

    with pytest.raises(StateError, match="inside the selected workspace"):
        WorkspaceStateStore(tmp_path).read()


def test_state_store_rejects_state_file_symlink(tmp_path: Path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text('{"schema_version": 1, "entries": {}}', encoding="utf-8")
    state_directory = tmp_path / ".ansiblectl"
    state_directory.mkdir()
    (state_directory / "state.json").symlink_to(outside)

    with pytest.raises(StateError, match="symbolic link"):
        WorkspaceStateStore(tmp_path).read()

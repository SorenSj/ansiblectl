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
    assert list((tmp_path / ".ansiblectl/transactions").glob("[!.]*")) == []


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


def test_state_invalidation_previews_then_removes_only_exact_entry(tmp_path: Path) -> None:
    store = WorkspaceStateStore(tmp_path)
    entries = {
        "inventory": CacheEntry("git:main", "revision changes", {"hosts": 2}),
        "plugins": CacheEntry("directory:plugins", "directory changes", {"count": 1}),
    }
    store.write(entries)

    preview = store.invalidate("inventory", apply=False)

    assert preview.existed is True
    assert preview.applied is False
    assert preview.remaining_count == 1
    assert store.read() == entries

    applied = store.invalidate("inventory", apply=True)

    assert applied.existed is True
    assert applied.applied is True
    assert applied.remaining_count == 1
    assert store.read() == {"plugins": entries["plugins"]}


def test_state_invalidation_rejects_empty_name(tmp_path: Path) -> None:
    with pytest.raises(StateError, match="name must be non-empty"):
        WorkspaceStateStore(tmp_path).invalidate("  ", apply=True)


def test_state_store_rejects_lock_file_symlink(tmp_path: Path) -> None:
    state_directory = tmp_path / ".ansiblectl"
    state_directory.mkdir()
    outside = tmp_path / "outside.lock"
    outside.touch()
    (state_directory / "state.lock").symlink_to(outside)

    with pytest.raises(StateError, match="lock must not be a symbolic link"):
        WorkspaceStateStore(tmp_path).invalidate("inventory", apply=True)

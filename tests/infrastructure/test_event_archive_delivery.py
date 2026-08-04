"""Immutable workspace event archive delivery adapter tests."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from ansiblectl.domain.durable_events import DurableEventEnvelope
from ansiblectl.domain.event_archive import WorkspaceEventArchive
from ansiblectl.domain.event_delivery import DeliveryOutcomeState
from ansiblectl.infrastructure import event_archive_delivery as delivery_module
from ansiblectl.infrastructure.event_archive_delivery import (
    ARCHIVE_UNAVAILABLE,
    WorkspaceEventArchiveDeliveryAdapter,
)


def envelope() -> DurableEventEnvelope:
    return DurableEventEnvelope(
        "00000000Z80000000000000000",
        7,
        "workspace.initialized",
        "2026-08-04T00:00:00.000000Z",
        None,
        {"project_name": "demo"},
    )


def adapter(tmp_path: Path) -> WorkspaceEventArchiveDeliveryAdapter:
    return WorkspaceEventArchiveDeliveryAdapter(tmp_path, WorkspaceEventArchive("audit.primary"))


def target(tmp_path: Path) -> Path:
    return (
        tmp_path
        / ".ansiblectl/events/archives/audit.primary"
        / "00000000000000000007-00000000Z80000000000000000.json"
    )


def test_adapter_durably_installs_one_exact_private_canonical_file(tmp_path: Path) -> None:
    outcome = adapter(tmp_path).deliver(envelope())

    assert outcome.state is DeliveryOutcomeState.DELIVERED
    archived = target(tmp_path)
    assert archived.read_bytes() == envelope().to_canonical_bytes()
    assert not archived.read_bytes().endswith(b"\n")
    assert stat.S_IMODE(archived.stat().st_mode) == 0o600
    for directory in (
        tmp_path / ".ansiblectl",
        tmp_path / ".ansiblectl/events",
        tmp_path / ".ansiblectl/events/archives",
        archived.parent,
    ):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert list(archived.parent.iterdir()) == [archived]


def test_exact_replay_succeeds_without_second_write_or_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = adapter(tmp_path)
    assert selected.deliver(envelope()).state is DeliveryOutcomeState.DELIVERED
    archived = target(tmp_path)
    before = archived.stat()

    def unexpected_write(descriptor: int, content: bytes) -> int:
        raise AssertionError("exact replay must not write")

    monkeypatch.setattr(os, "write", unexpected_write)

    outcome = selected.deliver(envelope())

    after = archived.stat()
    assert outcome.state is DeliveryOutcomeState.DELIVERED
    assert (after.st_ino, after.st_mtime_ns, after.st_ctime_ns) == (
        before.st_ino,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )


@pytest.mark.parametrize("unsafe", ["mismatch", "symlink", "hardlink", "permissions"])
def test_unsafe_existing_target_fails_closed_without_mutation(tmp_path: Path, unsafe: str) -> None:
    archived = target(tmp_path)
    archived.parent.mkdir(parents=True, mode=0o700)
    for directory in (
        tmp_path / ".ansiblectl",
        tmp_path / ".ansiblectl/events",
        tmp_path / ".ansiblectl/events/archives",
        archived.parent,
    ):
        directory.chmod(0o700)
    outside = tmp_path / "sentinel-outside"
    outside.write_bytes(b"sentinel-unsafe-content")
    if unsafe == "symlink":
        archived.symlink_to(outside)
    else:
        archived.write_bytes(b"mismatched-content")
        archived.chmod(0o600)
        if unsafe == "hardlink":
            os.link(archived, archived.with_name("second-link"))
        elif unsafe == "permissions":
            archived.chmod(0o640)
    before = outside.read_bytes() if unsafe == "symlink" else archived.read_bytes()

    outcome = adapter(tmp_path).deliver(envelope())

    assert outcome.failure_reason == ARCHIVE_UNAVAILABLE
    observed = outside.read_bytes() if unsafe == "symlink" else archived.read_bytes()
    assert observed == before


@pytest.mark.parametrize("component", ["private", "events", "archives", "archive"])
def test_unsafe_directory_component_fails_before_final_file(tmp_path: Path, component: str) -> None:
    paths = {
        "private": tmp_path / ".ansiblectl",
        "events": tmp_path / ".ansiblectl/events",
        "archives": tmp_path / ".ansiblectl/events/archives",
        "archive": tmp_path / ".ansiblectl/events/archives/audit.primary",
    }
    selected = paths[component]
    selected.mkdir(parents=True, mode=0o700)
    selected.chmod(0o750)

    outcome = adapter(tmp_path).deliver(envelope())

    assert outcome.failure_reason == ARCHIVE_UNAVAILABLE
    assert not target(tmp_path).exists()


def test_partial_writes_are_completed_before_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = os.write

    def partial(descriptor: int, content: bytes) -> int:
        return original(descriptor, content[: max(1, len(content) // 3)])

    monkeypatch.setattr(os, "write", partial)

    assert adapter(tmp_path).deliver(envelope()).state is DeliveryOutcomeState.DELIVERED
    assert target(tmp_path).read_bytes() == envelope().to_canonical_bytes()


def test_capability_and_operating_system_details_are_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = "sentinel-private-path ENOSPC staging-name payload-value"

    def unavailable() -> bool:
        raise OSError(sentinel)

    monkeypatch.setattr(delivery_module, "_has_required_capabilities", unavailable)

    outcome = adapter(tmp_path / "sentinel-private-path").deliver(envelope())

    assert outcome.failure_reason == ARCHIVE_UNAVAILABLE
    assert all(part not in repr(outcome) for part in sentinel.split())
    assert "sentinel-private-path" not in repr(adapter(tmp_path / "sentinel-private-path"))

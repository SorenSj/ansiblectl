"""Infrastructure tests for workspace filesystem capability probes."""

import stat
from pathlib import Path

import pytest

from ansiblectl.domain.filesystem import FilesystemCapabilityReason
from ansiblectl.infrastructure import filesystem_capabilities
from ansiblectl.infrastructure.filesystem_capabilities import inspect_filesystem_capabilities


def test_local_posix_filesystem_supports_required_capabilities(tmp_path: Path) -> None:
    report = inspect_filesystem_capabilities(tmp_path)

    assert report.supported is True
    assert report.scope_id is not None
    assert report.scope_id.startswith("filesystem:")
    assert report.reasons == ()
    private_root = tmp_path / ".ansiblectl"
    assert stat.S_IMODE(private_root.stat().st_mode) == 0o700
    assert list((private_root / "capability-probes").glob("probe-*")) == []


def test_probe_rejects_private_control_symlink_escape(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / ".ansiblectl").symlink_to(outside, target_is_directory=True)

    report = inspect_filesystem_capabilities(workspace)

    assert report.supported is False
    assert report.reasons == (FilesystemCapabilityReason.CONTROL_PATH_UNSAFE,)
    assert list(outside.iterdir()) == []


def test_probe_reports_non_posix_platform_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("ansiblectl.infrastructure.filesystem_capabilities.os.name", "nt")

    report = inspect_filesystem_capabilities(tmp_path)

    assert report.reasons == (FilesystemCapabilityReason.POSIX_REQUIRED,)
    assert not (tmp_path / ".ansiblectl").exists()


@pytest.mark.parametrize(
    "reason",
    [
        FilesystemCapabilityReason.ADVISORY_LOCKING_UNAVAILABLE,
        FilesystemCapabilityReason.ATOMIC_REPLACE_UNAVAILABLE,
        FilesystemCapabilityReason.FILE_SYNC_UNAVAILABLE,
        FilesystemCapabilityReason.DIRECTORY_SYNC_UNAVAILABLE,
    ],
)
def test_probe_preserves_stable_failure_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reason: FilesystemCapabilityReason,
) -> None:
    if reason is FilesystemCapabilityReason.ADVISORY_LOCKING_UNAVAILABLE:
        monkeypatch.setattr(filesystem_capabilities, "_probe_locking", lambda path: reason)
    else:
        monkeypatch.setattr(filesystem_capabilities, "_probe_locking", lambda path: None)
        monkeypatch.setattr(filesystem_capabilities, "_probe_replace_and_sync", lambda path: reason)

    report = inspect_filesystem_capabilities(tmp_path)

    assert report.supported is False
    assert report.reasons == (reason,)
    assert list((tmp_path / ".ansiblectl/capability-probes").glob("probe-*")) == []


def test_probe_reports_cleanup_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_cleanup(path: Path) -> None:
        raise OSError("simulated cleanup failure")

    monkeypatch.setattr(
        "ansiblectl.infrastructure.filesystem_capabilities.shutil.rmtree", fail_cleanup
    )

    report = inspect_filesystem_capabilities(tmp_path)

    assert report.reasons == (FilesystemCapabilityReason.PROBE_CLEANUP_FAILED,)

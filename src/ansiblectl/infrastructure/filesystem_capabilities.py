"""Workspace-scoped probes for transactional filesystem guarantees."""

from __future__ import annotations

import fcntl
import hashlib
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

from ansiblectl.domain.filesystem import (
    FilesystemCapabilityReason,
    FilesystemCapabilityReport,
)


def inspect_filesystem_capabilities(root: Path) -> FilesystemCapabilityReport:
    """Inspect required guarantees without modifying user-owned targets."""

    platform = sys.platform
    if os.name != "posix":
        return _unsupported(platform, FilesystemCapabilityReason.POSIX_REQUIRED)
    resolved_root = root.resolve()
    private_root = resolved_root / ".ansiblectl"
    try:
        if private_root.exists() and private_root.resolve() != private_root:
            return _unsupported(platform, FilesystemCapabilityReason.CONTROL_PATH_UNSAFE)
        private_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        private_root.chmod(0o700)
        if private_root.resolve() != private_root:
            return _unsupported(platform, FilesystemCapabilityReason.CONTROL_PATH_UNSAFE)
        scope_id = _scope_id(private_root)
    except OSError:
        return _unsupported(platform, FilesystemCapabilityReason.CONTROL_PATH_UNSAFE)

    probe_parent = private_root / "capability-probes"
    probe: Path | None = None
    reason: FilesystemCapabilityReason | None = None
    try:
        probe_parent.mkdir(mode=0o700, exist_ok=True)
        probe_parent.chmod(0o700)
        probe = Path(tempfile.mkdtemp(prefix="probe-", dir=probe_parent))
        probe.chmod(0o700)
        if stat.S_IMODE(probe.stat().st_mode) != 0o700:
            reason = FilesystemCapabilityReason.OWNER_PERMISSIONS_UNAVAILABLE
        else:
            reason = _probe_locking(probe)
        if reason is None:
            reason = _probe_replace_and_sync(probe)
    except OSError:
        reason = FilesystemCapabilityReason.CAPABILITY_PROBE_FAILED
    if probe is not None:
        try:
            shutil.rmtree(probe)
            _fsync_directory(probe_parent)
        except OSError:
            return _unsupported(platform, FilesystemCapabilityReason.PROBE_CLEANUP_FAILED, scope_id)
    if reason is not None:
        return _unsupported(platform, reason, scope_id)
    return FilesystemCapabilityReport(True, platform, scope_id)


def _probe_locking(probe: Path) -> FilesystemCapabilityReason | None:
    lock_path = probe / "owner.lock"
    first = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    second = os.open(lock_path, os.O_RDWR)
    try:
        fcntl.flock(first, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            fcntl.flock(second, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return None
        return FilesystemCapabilityReason.ADVISORY_LOCKING_UNAVAILABLE
    except OSError:
        return FilesystemCapabilityReason.ADVISORY_LOCKING_UNAVAILABLE
    finally:
        fcntl.flock(first, fcntl.LOCK_UN)
        os.close(second)
        os.close(first)


def _probe_replace_and_sync(probe: Path) -> FilesystemCapabilityReason | None:
    source = probe / "source"
    target = probe / "target"
    try:
        descriptor = os.open(source, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(b"ansiblectl-capability-probe")
            stream.flush()
            try:
                os.fsync(stream.fileno())
            except OSError:
                return FilesystemCapabilityReason.FILE_SYNC_UNAVAILABLE
        if stat.S_IMODE(source.stat().st_mode) != 0o600:
            return FilesystemCapabilityReason.OWNER_PERMISSIONS_UNAVAILABLE
        try:
            os.replace(source, target)
        except OSError:
            return FilesystemCapabilityReason.ATOMIC_REPLACE_UNAVAILABLE
        try:
            _fsync_directory(probe)
        except OSError:
            return FilesystemCapabilityReason.DIRECTORY_SYNC_UNAVAILABLE
        if target.read_bytes() != b"ansiblectl-capability-probe":
            return FilesystemCapabilityReason.ATOMIC_REPLACE_UNAVAILABLE
    except OSError:
        return FilesystemCapabilityReason.CAPABILITY_PROBE_FAILED
    return None


def _scope_id(path: Path) -> str:
    digest = hashlib.sha256(str(path.stat().st_dev).encode()).hexdigest()[:16]
    return f"filesystem:{digest}"


def _unsupported(
    platform: str,
    reason: FilesystemCapabilityReason,
    scope_id: str | None = None,
) -> FilesystemCapabilityReport:
    return FilesystemCapabilityReport(False, platform, scope_id, (reason,))


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

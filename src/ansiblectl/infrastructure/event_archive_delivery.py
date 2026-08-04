"""Durable immutable workspace event archive delivery adapter."""

from __future__ import annotations

import os
import re
import secrets
import stat
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

from ansiblectl.domain.durable_events import (
    MAX_DURABLE_EVENT_DELIVERY_BYTES,
    DurableEventEnvelope,
)
from ansiblectl.domain.event_archive import WorkspaceEventArchive
from ansiblectl.domain.event_delivery import DeliveryOutcome

ARCHIVE_UNAVAILABLE = "ARCHIVE_UNAVAILABLE"
_STAGING_PATTERN = re.compile(r"\.stage-[0-9a-f]{32}")


@dataclass(frozen=True, repr=False)
class WorkspaceEventArchiveDeliveryAdapter:
    """Install one canonical immutable file per delivered durable event."""

    workspace_root: Path = field(repr=False)
    archive: WorkspaceEventArchive = field(repr=False)
    checkpoint: Callable[[str], None] | None = field(default=None, repr=False, compare=False)

    def deliver(self, envelope: DurableEventEnvelope) -> DeliveryOutcome:
        try:
            target = self.archive.target_for(envelope)
            content = envelope.to_canonical_bytes()
            if len(content) > MAX_DURABLE_EVENT_DELIVERY_BYTES:
                raise OSError
            _install(
                self.workspace_root,
                target.archive_id,
                target.filename,
                content,
                self.checkpoint or (lambda _name: None),
            )
        except Exception:
            return DeliveryOutcome.failure(ARCHIVE_UNAVAILABLE)
        return DeliveryOutcome.success()

    def __repr__(self) -> str:
        return "WorkspaceEventArchiveDeliveryAdapter(workspace_root=<redacted>, archive=<redacted>)"


def _install(
    workspace_root: Path,
    archive_id: str,
    filename: str,
    content: bytes,
    checkpoint: Callable[[str], None],
) -> None:
    if not _has_required_capabilities():
        raise OSError
    descriptors: list[int] = []
    try:
        root_fd = _open_directory(workspace_root)
        descriptors.append(root_fd)
        root = os.fstat(root_fd)
        if not stat.S_ISDIR(root.st_mode):
            raise OSError
        parent_fd = root_fd
        for component in (".ansiblectl", "events", "archives", archive_id):
            directory_fd = _open_or_create_private_directory(component, parent_fd, root.st_dev)
            descriptors.append(directory_fd)
            parent_fd = directory_fd
        _install_or_verify(parent_fd, root.st_dev, filename, content, checkpoint)
    finally:
        for descriptor in reversed(descriptors):
            with suppress(OSError):
                os.close(descriptor)


def _has_required_capabilities() -> bool:
    return (
        all(hasattr(os, name) for name in ("O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW"))
        and all(
            function in os.supports_dir_fd
            for function in (os.open, os.mkdir, os.link, os.stat, os.unlink)
        )
        and all(function in os.supports_follow_symlinks for function in (os.link, os.stat))
    )


def _open_directory(path: str | Path, directory_fd: int | None = None) -> int:
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    if directory_fd is None:
        return os.open(path, flags)
    return os.open(path, flags, dir_fd=directory_fd)


def _open_or_create_private_directory(name: str, parent_fd: int, device: int) -> int:
    try:
        os.mkdir(name, 0o700, dir_fd=parent_fd)
        created = True
    except FileExistsError:
        created = False
    descriptor = _open_directory(name, parent_fd)
    if created:
        os.fchmod(descriptor, 0o700)
        os.fsync(parent_fd)
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or metadata.st_dev != device
    ):
        os.close(descriptor)
        raise OSError
    return descriptor


def _install_or_verify(
    directory_fd: int,
    device: int,
    filename: str,
    content: bytes,
    checkpoint: Callable[[str], None],
) -> None:
    try:
        _verify_existing(directory_fd, device, filename, content)
        return
    except FileNotFoundError:
        pass
    staging = f".stage-{secrets.token_hex(16)}"
    descriptor: int | None = None
    installed = False
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
        descriptor = os.open(staging, flags, 0o600, dir_fd=directory_fd)
        checkpoint("archive.staging_created")
        _write_all(descriptor, content)
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
        checkpoint("archive.content_synced")
        os.close(descriptor)
        descriptor = None
        try:
            os.link(
                staging,
                filename,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
            installed = True
            checkpoint("archive.target_linked")
        except FileExistsError:
            pass
        with suppress(FileNotFoundError):
            os.unlink(staging, dir_fd=directory_fd)
        staging = ""
        checkpoint("archive.target_installed")
        os.fsync(directory_fd)
        checkpoint("archive.directory_synced")
        _verify_existing(directory_fd, device, filename, content)
    finally:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
        if staging:
            with suppress(OSError):
                os.unlink(staging, dir_fd=directory_fd)
        if installed:
            with suppress(OSError):
                os.fsync(directory_fd)


def _write_all(descriptor: int, content: bytes) -> None:
    offset = 0
    while offset < len(content):
        written = os.write(descriptor, content[offset:])
        if written < 1:
            raise OSError
        offset += written


def _verify_existing(directory_fd: int, device: int, filename: str, expected: bytes) -> None:
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    descriptor = os.open(filename, flags, dir_fd=directory_fd)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink not in {1, 2}
            or metadata.st_dev != device
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size != len(expected)
        ):
            raise OSError
        chunks: list[bytes] = []
        remaining = len(expected) + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        if b"".join(chunks) != expected:
            raise OSError
        if metadata.st_nlink == 2:
            _remove_matching_staging_link(directory_fd, metadata)
            os.fsync(directory_fd)
            if os.fstat(descriptor).st_nlink != 1:
                raise OSError
    finally:
        os.close(descriptor)


def _remove_matching_staging_link(directory_fd: int, target: os.stat_result) -> None:
    matches: list[str] = []
    for name in os.listdir(directory_fd):
        if _STAGING_PATTERN.fullmatch(name) is None:
            continue
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if metadata.st_dev == target.st_dev and metadata.st_ino == target.st_ino:
            matches.append(name)
    if len(matches) != 1:
        raise OSError
    os.unlink(matches[0], dir_fd=directory_fd)


__all__ = ["ARCHIVE_UNAVAILABLE", "WorkspaceEventArchiveDeliveryAdapter"]

"""Fail-closed workspace Unix-domain socket event delivery."""

from __future__ import annotations

import os
import select
import socket
import stat
import struct
import sys
import time
from collections.abc import Callable
from contextlib import suppress
from ctypes import CDLL, POINTER, byref, c_int, c_uint
from dataclasses import dataclass, field
from pathlib import Path

from ansiblectl.domain.durable_events import DurableEventEnvelope
from ansiblectl.domain.event_delivery import DeliveryOutcome
from ansiblectl.domain.unix_socket_delivery import (
    UNIX_SOCKET_DEADLINE_SECONDS,
    WorkspaceUnixSocket,
    WorkspaceUnixSocketRequest,
)

SOCKET_UNAVAILABLE = "SOCKET_UNAVAILABLE"
_ADDRESS_LIMITS = {"darwin": 103, "linux": 107}


@dataclass(frozen=True, repr=False)
class WorkspaceUnixSocketDeliveryAdapter:
    """Deliver one canonical envelope to one private same-user local receiver."""

    workspace_root: Path = field(repr=False)
    selection: WorkspaceUnixSocket = field(repr=False)
    socket_factory: Callable[[], socket.socket] = field(
        default=lambda: socket.socket(socket.AF_UNIX, socket.SOCK_STREAM),
        repr=False,
        compare=False,
    )
    clock: Callable[[], float] = field(default=time.monotonic, repr=False, compare=False)
    checkpoint: Callable[[str], None] | None = field(default=None, repr=False, compare=False)

    def deliver(self, envelope: DurableEventEnvelope) -> DeliveryOutcome:
        try:
            request = self.selection.request_for(envelope)
            path, fingerprint = _prepare_target(self.workspace_root, self.selection.target.filename)
            checkpoint = self.checkpoint or (lambda _name: None)
            checkpoint("socket.target_prepared")
            connection = self.socket_factory()
            try:
                deadline = self.clock() + UNIX_SOCKET_DEADLINE_SECONDS
                _set_remaining_timeout(connection, deadline, self.clock)
                connection.connect(os.fspath(path))
                checkpoint("socket.connected")
                if _peer_uid(connection) != os.geteuid():
                    raise OSError
                _verify_target(path, fingerprint)
                checkpoint("socket.peer_verified")
                _exchange(connection, request, deadline, self.clock, checkpoint)
            finally:
                connection.close()
        except Exception:
            return DeliveryOutcome.failure(SOCKET_UNAVAILABLE)
        return DeliveryOutcome.success()

    def __repr__(self) -> str:
        return "WorkspaceUnixSocketDeliveryAdapter(workspace_root=<redacted>, selection=<redacted>)"


def _prepare_target(workspace_root: Path, filename: str) -> tuple[Path, tuple[int, int]]:
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
        for component in (".ansiblectl", "events", "sockets"):
            directory_fd = _open_or_create_private_directory(component, parent_fd, root.st_dev)
            descriptors.append(directory_fd)
            parent_fd = directory_fd
        metadata = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
        _validate_socket_metadata(metadata, root.st_dev)
        path = workspace_root / ".ansiblectl" / "events" / "sockets" / filename
        _validate_address(path)
        return path, (metadata.st_dev, metadata.st_ino)
    finally:
        for descriptor in reversed(descriptors):
            with suppress(OSError):
                os.close(descriptor)


def _verify_target(path: Path, expected: tuple[int, int]) -> None:
    metadata = path.lstat()
    _validate_socket_metadata(metadata, expected[0])
    if (metadata.st_dev, metadata.st_ino) != expected:
        raise OSError


def _validate_socket_metadata(metadata: os.stat_result, device: int) -> None:
    if (
        not stat.S_ISSOCK(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_dev != device
    ):
        raise OSError


def _validate_address(path: Path) -> None:
    limit = _ADDRESS_LIMITS.get(sys.platform)
    encoded = os.fsencode(os.fspath(path))
    if limit is None or not encoded or b"\x00" in encoded or len(encoded) > limit:
        raise OSError


def _has_required_capabilities() -> bool:
    return (
        sys.platform in _ADDRESS_LIMITS
        and all(hasattr(os, name) for name in ("O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW"))
        and all(function in os.supports_dir_fd for function in (os.open, os.mkdir, os.stat))
        and os.stat in os.supports_follow_symlinks
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


def _peer_uid(connection: socket.socket) -> int:
    if sys.platform == "linux" and hasattr(socket, "SO_PEERCRED"):
        credentials = connection.getsockopt(
            socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
        )
        _pid, uid, _gid = struct.unpack("3i", credentials)
        return int(uid)
    if sys.platform == "darwin":
        libc = CDLL(None, use_errno=True)
        getpeereid = libc.getpeereid
        getpeereid.argtypes = (c_int, POINTER(c_uint), POINTER(c_uint))
        getpeereid.restype = c_int
        uid = c_uint()
        gid = c_uint()
        if getpeereid(connection.fileno(), byref(uid), byref(gid)) == 0:
            return uid.value
    raise OSError


def _exchange(
    connection: socket.socket,
    request: WorkspaceUnixSocketRequest,
    deadline: float,
    clock: Callable[[], float],
    checkpoint: Callable[[str], None] = lambda _name: None,
) -> None:
    _send_all(connection, request.frame[:4], deadline, clock)
    _reject_early_response(connection)
    _send_all(connection, request.frame[4:], deadline, clock, reject_response=True)
    connection.shutdown(socket.SHUT_WR)
    checkpoint("socket.request_sent")
    response = _receive_exact(connection, len(request.acknowledgement) + 1, deadline, clock)
    if response != request.acknowledgement:
        raise OSError
    checkpoint("socket.ack_received")
    _set_remaining_timeout(connection, deadline, clock)
    if connection.recv(1) != b"":
        raise OSError


def _send_all(
    connection: socket.socket,
    content: bytes,
    deadline: float,
    clock: Callable[[], float],
    *,
    reject_response: bool = False,
) -> None:
    offset = 0
    while offset < len(content):
        _set_remaining_timeout(connection, deadline, clock)
        written = connection.send(content[offset:])
        if written < 1:
            raise OSError
        offset += written
        if reject_response and offset < len(content):
            _reject_early_response(connection)


def _reject_early_response(connection: socket.socket) -> None:
    readable, _, _ = select.select([connection], [], [], 0)
    if readable:
        raise OSError


def _receive_exact(
    connection: socket.socket,
    maximum: int,
    deadline: float,
    clock: Callable[[], float],
) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while size < maximum:
        _set_remaining_timeout(connection, deadline, clock)
        chunk = connection.recv(maximum - size)
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
    return b"".join(chunks)


def _set_remaining_timeout(
    connection: socket.socket, deadline: float, clock: Callable[[], float]
) -> None:
    remaining = deadline - clock()
    if remaining <= 0:
        raise TimeoutError
    connection.settimeout(remaining)


__all__ = ["SOCKET_UNAVAILABLE", "WorkspaceUnixSocketDeliveryAdapter"]

"""Workspace Unix-domain socket delivery adapter tests."""

from __future__ import annotations

import os
import shutil
import socket
import stat
import sys
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

import pytest

from ansiblectl.domain.durable_events import DurableEventEnvelope
from ansiblectl.domain.event_delivery import DeliveryOutcomeState
from ansiblectl.domain.unix_socket_delivery import WorkspaceUnixSocket
from ansiblectl.infrastructure import unix_socket_delivery as delivery_module
from ansiblectl.infrastructure.unix_socket_delivery import (
    SOCKET_UNAVAILABLE,
    WorkspaceUnixSocketDeliveryAdapter,
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


@pytest.fixture
def workspace() -> Iterator[Path]:
    root = Path(tempfile.mkdtemp(prefix="ac-", dir="/tmp"))
    try:
        yield root
    finally:
        shutil.rmtree(root)


def adapter(workspace: Path) -> WorkspaceUnixSocketDeliveryAdapter:
    return WorkspaceUnixSocketDeliveryAdapter(workspace, WorkspaceUnixSocket("audit"))


def target(workspace: Path) -> Path:
    return workspace / ".ansiblectl/events/sockets/audit.sock"


@contextmanager
def receiver(workspace: Path, response: bytes | None = None) -> Iterator[list[bytes]]:
    path = target(workspace)
    path.parent.mkdir(parents=True, mode=0o700)
    for directory in (path.parents[2], path.parents[1], path.parent):
        directory.chmod(0o700)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(os.fspath(path))
    path.chmod(0o600)
    listener.listen(1)
    received: list[bytes] = []

    def serve() -> None:
        connection, _ = listener.accept()
        with connection:
            prefix = _read_exact(connection, 4)
            if len(prefix) != 4:
                return
            size = int.from_bytes(prefix, "big")
            body = _read_exact(connection, size)
            if len(body) != size:
                return
            received.append(prefix + body)
            assert connection.recv(1) == b""
            reply = response if response is not None else f"ACK {envelope().event_id}\n".encode()
            with suppress(OSError):
                connection.sendall(reply)

    thread = threading.Thread(target=serve)
    thread.start()
    try:
        yield received
    finally:
        thread.join(timeout=5)
        listener.close()
        assert not thread.is_alive()


def _read_exact(connection: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    while sum(map(len, chunks)) < size:
        chunk = connection.recv(size - sum(map(len, chunks)))
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def test_adapter_delivers_exact_frame_to_private_same_user_receiver(workspace: Path) -> None:
    with receiver(workspace) as received:
        outcome = adapter(workspace).deliver(envelope())

    body = envelope().to_canonical_bytes()
    assert outcome.state is DeliveryOutcomeState.DELIVERED
    assert received == [len(body).to_bytes(4, "big") + body]
    assert stat.S_IMODE(target(workspace).stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "response",
    [
        b"",
        b"ACK 00000000Z80000000000000001\n",
        b"ACK 00000000Z80000000000000000",
        b"ACK 00000000Z80000000000000000\nextra",
    ],
)
def test_adapter_rejects_every_noncanonical_acknowledgement(
    workspace: Path, response: bytes
) -> None:
    with receiver(workspace, response):
        outcome = adapter(workspace).deliver(envelope())

    assert outcome.failure_reason == SOCKET_UNAVAILABLE


@pytest.mark.parametrize("unsafe", ["absent", "regular", "symlink", "permissions"])
def test_adapter_rejects_unsafe_socket_targets(workspace: Path, unsafe: str) -> None:
    path = target(workspace)
    path.parent.mkdir(parents=True, mode=0o700)
    for directory in (path.parents[2], path.parents[1], path.parent):
        directory.chmod(0o700)
    if unsafe == "regular":
        path.write_bytes(b"sentinel")
        path.chmod(0o600)
    elif unsafe == "symlink":
        path.symlink_to(workspace / "sentinel")
    elif unsafe == "permissions":
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(os.fspath(path))
        path.chmod(0o660)
    else:
        listener = None

    outcome = adapter(workspace).deliver(envelope())

    assert outcome.failure_reason == SOCKET_UNAVAILABLE
    if unsafe == "permissions":
        assert listener is not None
        listener.close()


def test_adapter_rejects_wrong_connected_peer_and_redacts_details(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = "sentinel-private-peer-path"
    monkeypatch.setattr(delivery_module, "_peer_uid", lambda _connection: os.geteuid() + 1)

    with receiver(workspace):
        outcome = adapter(workspace).deliver(envelope())

    assert outcome.failure_reason == SOCKET_UNAVAILABLE
    selected = WorkspaceUnixSocketDeliveryAdapter(
        workspace / sentinel, WorkspaceUnixSocket("sentinel.peer")
    )
    assert sentinel not in repr(selected)
    assert "sentinel.peer" not in repr(selected)


def test_adapter_rejects_overlong_address_before_connection(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = target(workspace)
    path.parent.mkdir(parents=True, mode=0o700)
    for directory in (path.parents[2], path.parents[1], path.parent):
        directory.chmod(0o700)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(os.fspath(path))
    path.chmod(0o600)
    monkeypatch.setitem(delivery_module._ADDRESS_LIMITS, sys.platform, 1)

    outcome = adapter(workspace).deliver(envelope())

    listener.close()
    assert outcome.failure_reason == SOCKET_UNAVAILABLE

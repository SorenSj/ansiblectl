"""Workspace Unix-domain socket delivery adapter tests."""

from __future__ import annotations

import os
import select
import shutil
import socket
import stat
import sys
import tempfile
import threading
import time
from collections.abc import Buffer, Iterator
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


class FragmentedSocket(socket.socket):
    """Real socket constrained to deterministic short I/O operations."""

    def __init__(self) -> None:
        super().__init__(socket.AF_UNIX, socket.SOCK_STREAM)

    def send(self, data: Buffer, flags: int = 0) -> int:
        return super().send(memoryview(data)[:3], flags)

    def recv(self, bufsize: int, flags: int = 0) -> bytes:
        return super().recv(min(bufsize, 2), flags)


def test_adapter_completes_fragmented_request_and_acknowledgement_io(workspace: Path) -> None:
    selected = WorkspaceUnixSocketDeliveryAdapter(
        workspace, WorkspaceUnixSocket("audit"), socket_factory=FragmentedSocket
    )

    with receiver(workspace) as received:
        outcome = selected.deliver(envelope())

    body = envelope().to_canonical_bytes()
    assert outcome.state is DeliveryOutcomeState.DELIVERED
    assert received == [len(body).to_bytes(4, "big") + body]


def test_adapter_rejects_target_replacement_after_connect(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_peer_uid = delivery_module._peer_uid

    def replace_target(connection: socket.socket) -> int:
        uid = original_peer_uid(connection)
        target(workspace).unlink()
        target(workspace).write_bytes(b"sentinel-replacement")
        target(workspace).chmod(0o600)
        return uid

    monkeypatch.setattr(delivery_module, "_peer_uid", replace_target)

    with receiver(workspace):
        outcome = adapter(workspace).deliver(envelope())

    assert outcome.failure_reason == SOCKET_UNAVAILABLE
    assert target(workspace).read_bytes() == b"sentinel-replacement"


def test_adapter_fails_closed_when_platform_capabilities_are_unavailable(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(delivery_module, "_has_required_capabilities", lambda: False)

    outcome = adapter(workspace).deliver(envelope())

    assert outcome.failure_reason == SOCKET_UNAVAILABLE
    assert not target(workspace).exists()


def test_exchange_rejects_response_before_body_send(monkeypatch: pytest.MonkeyPatch) -> None:
    client, server = socket.socketpair()
    request = WorkspaceUnixSocket("audit").request_for(envelope())
    monkeypatch.setattr(select, "select", lambda *_args: ([client], [], []))
    try:
        with pytest.raises(OSError):
            delivery_module._exchange(client, request, time.monotonic() + 1, time.monotonic)
        assert server.recv(4) == request.frame[:4]
    finally:
        client.close()
        server.close()


def test_adapter_applies_one_deadline_to_stalled_acknowledgement(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = target(workspace)
    path.parent.mkdir(parents=True, mode=0o700)
    for directory in (path.parents[2], path.parents[1], path.parent):
        directory.chmod(0o700)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(os.fspath(path))
    path.chmod(0o600)
    listener.listen(1)
    monkeypatch.setattr(delivery_module, "UNIX_SOCKET_DEADLINE_SECONDS", 0.05)

    def stall() -> None:
        connection, _ = listener.accept()
        with connection:
            prefix = _read_exact(connection, 4)
            _read_exact(connection, int.from_bytes(prefix, "big"))
            assert connection.recv(1) == b""
            time.sleep(0.15)

    thread = threading.Thread(target=stall)
    thread.start()
    started = time.monotonic()
    outcome = adapter(workspace).deliver(envelope())
    elapsed = time.monotonic() - started
    thread.join(timeout=2)
    listener.close()

    assert outcome.failure_reason == SOCKET_UNAVAILABLE
    assert 0.03 <= elapsed < 0.14
    assert not thread.is_alive()

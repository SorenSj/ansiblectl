"""Real process-termination tests for workspace Unix-socket delivery."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ansiblectl.application.event_delivery import EventDeliveryService
from ansiblectl.domain.durable_events import DurableEventEnvelope
from ansiblectl.domain.event_delivery import DeliveryRetryProfile, DeliveryRunState
from ansiblectl.domain.events import Event
from ansiblectl.domain.unix_socket_delivery import WorkspaceUnixSocket
from ansiblectl.infrastructure.event_outbox import SqliteEventOutbox
from ansiblectl.infrastructure.unix_socket_delivery import WorkspaceUnixSocketDeliveryAdapter

_CRASH_EXIT = 86
_NOW = datetime(2026, 8, 4, tzinfo=UTC)
_PROFILE = DeliveryRetryProfile(3, (10, 30), 30)
_DELIVERY_CHILD = """
import os
import sys
from pathlib import Path

from ansiblectl.domain.durable_events import DurableEventEnvelope
from ansiblectl.domain.unix_socket_delivery import WorkspaceUnixSocket
from ansiblectl.infrastructure.unix_socket_delivery import WorkspaceUnixSocketDeliveryAdapter

root = Path(sys.argv[1])
selected = sys.argv[2]

def checkpoint(name: str) -> None:
    if name == selected:
        os._exit(86)

event = DurableEventEnvelope(
    "00000000Z80000000000000000",
    7,
    "workspace.initialized",
    "2026-08-04T00:00:00.000000Z",
    None,
    {"project_name": "demo"},
)
WorkspaceUnixSocketDeliveryAdapter(
    root, WorkspaceUnixSocket("audit"), checkpoint=checkpoint
).deliver(event)
"""
_ACK_CHILD = """
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from ansiblectl.application.event_delivery import EventDeliveryService
from ansiblectl.domain.event_delivery import DeliveryRetryProfile
from ansiblectl.domain.unix_socket_delivery import WorkspaceUnixSocket
from ansiblectl.infrastructure.event_outbox import SqliteEventOutbox
from ansiblectl.infrastructure.unix_socket_delivery import WorkspaceUnixSocketDeliveryAdapter

root = Path(sys.argv[1])
adapter = WorkspaceUnixSocketDeliveryAdapter(root, WorkspaceUnixSocket("audit"))

class CrashAfterReceiverAck:
    def deliver(self, envelope):
        outcome = adapter.deliver(envelope)
        if outcome.failure_reason is None:
            os._exit(86)
        return outcome

service = EventDeliveryService(
    SqliteEventOutbox(root),
    CrashAfterReceiverAck(),
    DeliveryRetryProfile(3, (10, 30), 30),
    lambda: datetime(2026, 8, 4, tzinfo=UTC),
)
service.step("socket")
"""


@pytest.fixture
def workspace() -> Iterator[Path]:
    root = Path(tempfile.mkdtemp(prefix="ac-rel-", dir="/tmp"))
    try:
        yield root
    finally:
        shutil.rmtree(root)


def _environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path.cwd() / "src")
    return environment


def _target(root: Path) -> Path:
    return root / ".ansiblectl/events/sockets/audit.sock"


@contextmanager
def _receiver(root: Path) -> Iterator[list[bytes]]:
    path = _target(root)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    for directory in (path.parents[2], path.parents[1], path.parent):
        directory.chmod(0o700)
    with suppress(FileNotFoundError):
        path.unlink()
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(os.fspath(path))
    path.chmod(0o600)
    listener.listen(1)
    received: list[bytes] = []
    errors: list[BaseException] = []

    def serve() -> None:
        try:
            connection, _ = listener.accept()
            with connection:
                prefix = _read_exact(connection, 4)
                if len(prefix) != 4:
                    return
                body = _read_exact(connection, int.from_bytes(prefix, "big"))
                if len(body) != int.from_bytes(prefix, "big"):
                    return
                received.append(body)
                connection.recv(1)
                with suppress(OSError):
                    connection.sendall(b"ACK 00000000Z80000000000000000\n")
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=serve)
    thread.start()
    try:
        yield received
    finally:
        thread.join(timeout=5)
        listener.close()
        assert not thread.is_alive()
        assert errors == []


def _read_exact(connection: socket.socket, size: int) -> bytes:
    content = bytearray()
    while len(content) < size:
        chunk = connection.recv(size - len(content))
        if not chunk:
            break
        content.extend(chunk)
    return bytes(content)


@pytest.mark.parametrize(
    "checkpoint",
    [
        "socket.connected",
        "socket.peer_verified",
        "socket.request_sent",
        "socket.ack_received",
    ],
)
def test_new_process_can_retry_after_real_sender_termination(
    workspace: Path, checkpoint: str
) -> None:
    with _receiver(workspace) as first_received:
        child = subprocess.run(
            (sys.executable, "-c", _DELIVERY_CHILD, str(workspace), checkpoint),
            env=_environment(),
            check=False,
            capture_output=True,
            timeout=10,
        )

    assert child.returncode == _CRASH_EXIT
    assert child.stdout == b""
    assert child.stderr == b""
    with _receiver(workspace) as retried:
        outcome = WorkspaceUnixSocketDeliveryAdapter(
            workspace, WorkspaceUnixSocket("audit")
        ).deliver(envelope())
    assert outcome.failure_reason is None
    assert len(retried) == 1
    if checkpoint in {"socket.request_sent", "socket.ack_received"}:
        assert len(first_received) == 1


def envelope() -> DurableEventEnvelope:
    return DurableEventEnvelope(
        "00000000Z80000000000000000",
        7,
        "workspace.initialized",
        "2026-08-04T00:00:00.000000Z",
        None,
        {"project_name": "demo"},
    )


def test_receiver_ack_outbox_ack_crash_boundary_replays_same_event(workspace: Path) -> None:
    outbox = SqliteEventOutbox(workspace)
    outbox.append(
        Event("workspace.initialized", {"project_name": "demo"}),
        event_id="00000000Z80000000000000000",
        occurred_at="2026-08-04T00:00:00.000000Z",
    )
    outbox.register_consumer("socket")
    with _receiver(workspace) as first_received:
        child = subprocess.run(
            (sys.executable, "-c", _ACK_CHILD, str(workspace)),
            env=_environment(),
            check=False,
            capture_output=True,
            timeout=10,
        )

    assert child.returncode == _CRASH_EXIT
    service = EventDeliveryService(
        outbox,
        WorkspaceUnixSocketDeliveryAdapter(workspace, WorkspaceUnixSocket("audit")),
        _PROFILE,
        lambda: _NOW + timedelta(seconds=31),
    )
    with _receiver(workspace) as retried:
        result = service.step("socket")

    assert result.state is DeliveryRunState.DELIVERED
    assert len(first_received) == len(retried) == 1
    assert first_received == retried
    assert service.step("socket").state is DeliveryRunState.IDLE

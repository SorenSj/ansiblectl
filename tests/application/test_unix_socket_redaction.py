"""End-to-end redaction tests for workspace Unix-socket delivery failures."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from ansiblectl.application.event_delivery import EventDeliveryService
from ansiblectl.domain.event_delivery import DeliveryRetryProfile
from ansiblectl.domain.events import Event
from ansiblectl.domain.unix_socket_delivery import WorkspaceUnixSocket
from ansiblectl.infrastructure import unix_socket_delivery as delivery_module
from ansiblectl.infrastructure.event_outbox import SqliteEventOutbox
from ansiblectl.infrastructure.unix_socket_delivery import (
    SOCKET_UNAVAILABLE,
    WorkspaceUnixSocketDeliveryAdapter,
)

_NOW = datetime(2026, 8, 4, tzinfo=UTC)


def test_socket_failure_details_never_reach_public_or_durable_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    socket_id = "sentinel.private.socket"
    payload = "sentinel-private-socket-payload"
    details = "sentinel-path peer-501 mode-0660 protocol-secret timeout-detail exception-value"
    outbox = SqliteEventOutbox(tmp_path)
    outbox.append(Event("workspace.initialized", {"value": payload}))
    outbox.register_consumer("socket-consumer")
    database_path = tmp_path / ".ansiblectl/events/outbox.sqlite3"
    payload_copies_before = database_path.read_bytes().count(payload.encode())

    def fail_target(*args: object, **kwargs: object) -> None:
        raise OSError(details)

    monkeypatch.setattr(delivery_module, "_prepare_target", fail_target)
    adapter = WorkspaceUnixSocketDeliveryAdapter(
        tmp_path / "sentinel-path", WorkspaceUnixSocket(socket_id)
    )
    service = EventDeliveryService(
        outbox,
        adapter,
        DeliveryRetryProfile(3, (10, 30), 30),
        lambda: _NOW,
    )

    result = service.step("socket-consumer")

    assert result.failure_reason == SOCKET_UNAVAILABLE
    status = outbox.inspect_consumers(now=_NOW)[0]
    surfaces = (repr(adapter), repr(result), str(result.to_payload()), repr(status))
    database = database_path.read_bytes()
    for sentinel in (socket_id, *details.split()):
        assert all(sentinel not in surface for surface in surfaces)
        assert sentinel.encode() not in database
    assert all(payload not in surface for surface in surfaces)
    assert database.count(payload.encode()) == payload_copies_before

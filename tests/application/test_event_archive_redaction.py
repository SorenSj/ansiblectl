"""End-to-end redaction tests for workspace event archive delivery failures."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from ansiblectl.application.event_delivery import EventDeliveryService
from ansiblectl.domain.event_archive import WorkspaceEventArchive
from ansiblectl.domain.event_delivery import DeliveryRetryProfile
from ansiblectl.domain.events import Event
from ansiblectl.infrastructure import event_archive_delivery as delivery_module
from ansiblectl.infrastructure.event_archive_delivery import (
    ARCHIVE_UNAVAILABLE,
    WorkspaceEventArchiveDeliveryAdapter,
)
from ansiblectl.infrastructure.event_outbox import SqliteEventOutbox

_NOW = datetime(2026, 8, 4, tzinfo=UTC)


def test_archive_failure_details_never_reach_public_or_durable_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_id = "sentinel.private.archive"
    payload = "sentinel-private-event-payload"
    filesystem_details = "sentinel-path ENOSPC mode-0755 staging-secret exception-detail"
    outbox = SqliteEventOutbox(tmp_path)
    outbox.append(Event("workspace.initialized", {"value": payload}))
    outbox.register_consumer("archive-consumer")
    database_path = tmp_path / ".ansiblectl/events/outbox.sqlite3"
    payload_copies_before = database_path.read_bytes().count(payload.encode())

    def fail_install(*args: object, **kwargs: object) -> None:
        raise OSError(filesystem_details)

    monkeypatch.setattr(delivery_module, "_install", fail_install)
    adapter = WorkspaceEventArchiveDeliveryAdapter(
        tmp_path / "sentinel-path", WorkspaceEventArchive(archive_id)
    )
    service = EventDeliveryService(
        outbox,
        adapter,
        DeliveryRetryProfile(3, (10, 30), 30),
        lambda: _NOW,
    )

    result = service.step("archive-consumer")

    assert result.failure_reason == ARCHIVE_UNAVAILABLE
    status = outbox.inspect_consumers(now=_NOW)[0]
    surfaces = (repr(adapter), repr(result), str(result.to_payload()), repr(status))
    database = database_path.read_bytes()
    for sentinel in (archive_id, *filesystem_details.split()):
        assert all(sentinel not in surface for surface in surfaces)
        assert sentinel.encode() not in database
    assert all(payload not in surface for surface in surfaces)
    assert database.count(payload.encode()) == payload_copies_before

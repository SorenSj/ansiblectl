"""Real process-termination tests for workspace event archive durability."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ansiblectl.application.event_delivery import EventDeliveryService
from ansiblectl.domain.durable_events import DurableEventEnvelope
from ansiblectl.domain.event_archive import WorkspaceEventArchive
from ansiblectl.domain.event_delivery import DeliveryRetryProfile, DeliveryRunState
from ansiblectl.domain.events import Event
from ansiblectl.infrastructure.event_archive_delivery import WorkspaceEventArchiveDeliveryAdapter
from ansiblectl.infrastructure.event_outbox import SqliteEventOutbox

_CRASH_EXIT = 86
_NOW = datetime(2026, 8, 4, tzinfo=UTC)
_PROFILE = DeliveryRetryProfile(3, (10, 30), 30)
_WRITER_CHILD = """
import os
import sys
from pathlib import Path

from ansiblectl.domain.durable_events import DurableEventEnvelope
from ansiblectl.domain.event_archive import WorkspaceEventArchive
from ansiblectl.infrastructure.event_archive_delivery import WorkspaceEventArchiveDeliveryAdapter

root = Path(sys.argv[1])
selected = sys.argv[2]

def checkpoint(name: str) -> None:
    if name == selected:
        os._exit(86)

envelope = DurableEventEnvelope(
    "00000000Z80000000000000000",
    7,
    "workspace.initialized",
    "2026-08-04T00:00:00.000000Z",
    None,
    {"project_name": "demo"},
)
WorkspaceEventArchiveDeliveryAdapter(
    root, WorkspaceEventArchive("audit"), checkpoint
).deliver(envelope)
"""
_ACK_CHILD = """
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from ansiblectl.application.event_delivery import EventDeliveryService
from ansiblectl.domain.event_archive import WorkspaceEventArchive
from ansiblectl.domain.event_delivery import DeliveryRetryProfile
from ansiblectl.infrastructure.event_archive_delivery import WorkspaceEventArchiveDeliveryAdapter
from ansiblectl.infrastructure.event_outbox import SqliteEventOutbox

root = Path(sys.argv[1])
archive = WorkspaceEventArchiveDeliveryAdapter(root, WorkspaceEventArchive("audit"))

class CrashAfterArchive:
    def deliver(self, envelope):
        outcome = archive.deliver(envelope)
        if outcome.failure_reason is None:
            os._exit(86)
        return outcome

service = EventDeliveryService(
    SqliteEventOutbox(root),
    CrashAfterArchive(),
    DeliveryRetryProfile(3, (10, 30), 30),
    lambda: datetime(2026, 8, 4, tzinfo=UTC),
)
service.step("archive")
"""


def _environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path.cwd() / "src")
    return environment


def _target(root: Path, sequence: int = 7, event_id: str = "00000000Z80000000000000000") -> Path:
    return root / ".ansiblectl/events/archives/audit" / f"{sequence:020d}-{event_id}.json"


@pytest.mark.parametrize(
    "checkpoint",
    [
        "archive.staging_created",
        "archive.content_synced",
        "archive.target_linked",
        "archive.target_installed",
        "archive.directory_synced",
    ],
)
def test_new_process_replays_safely_after_real_writer_termination(
    tmp_path: Path, checkpoint: str
) -> None:
    child = subprocess.run(
        (sys.executable, "-c", _WRITER_CHILD, str(tmp_path), checkpoint),
        env=_environment(),
        check=False,
        capture_output=True,
        timeout=10,
    )

    assert child.returncode == _CRASH_EXIT
    assert child.stdout == b""
    assert child.stderr == b""

    adapter = WorkspaceEventArchiveDeliveryAdapter(tmp_path, WorkspaceEventArchive("audit"))
    durable = DurableEventEnvelope(
        "00000000Z80000000000000000",
        7,
        "workspace.initialized",
        "2026-08-04T00:00:00.000000Z",
        None,
        {"project_name": "demo"},
    )
    assert adapter.deliver(durable).failure_reason is None
    assert _target(tmp_path).read_bytes() == durable.to_canonical_bytes()
    assert _target(tmp_path).stat().st_nlink == 1


def test_archive_replay_closes_real_archive_write_outbox_ack_crash_boundary(
    tmp_path: Path,
) -> None:
    outbox = SqliteEventOutbox(tmp_path)
    archived = outbox.append(
        Event("workspace.initialized", {"project_name": "demo"}),
        event_id="00000000Z80000000000000000",
        occurred_at="2026-08-04T00:00:00.000000Z",
    )
    outbox.register_consumer("archive")
    child = subprocess.run(
        (sys.executable, "-c", _ACK_CHILD, str(tmp_path)),
        env=_environment(),
        check=False,
        capture_output=True,
        timeout=10,
    )

    assert child.returncode == _CRASH_EXIT
    before = _target(tmp_path, archived.sequence, archived.event_id).stat()
    service = EventDeliveryService(
        outbox,
        WorkspaceEventArchiveDeliveryAdapter(tmp_path, WorkspaceEventArchive("audit")),
        _PROFILE,
        lambda: _NOW + timedelta(seconds=31),
    )

    result = service.step("archive")

    after = _target(tmp_path, archived.sequence, archived.event_id).stat()
    assert result.state is DeliveryRunState.DELIVERED
    assert (after.st_ino, after.st_mtime_ns) == (before.st_ino, before.st_mtime_ns)
    assert service.step("archive").state is DeliveryRunState.IDLE

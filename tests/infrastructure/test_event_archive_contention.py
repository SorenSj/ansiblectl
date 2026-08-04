"""Multiprocess contention tests for immutable workspace event archives."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from ansiblectl.domain.durable_events import DurableEventEnvelope

_CHILD = """
import sys
from pathlib import Path

from ansiblectl.domain.durable_events import DurableEventEnvelope
from ansiblectl.domain.event_archive import WorkspaceEventArchive
from ansiblectl.infrastructure.event_archive_delivery import WorkspaceEventArchiveDeliveryAdapter

root = Path(sys.argv[1])
sequence = int(sys.argv[2])
event_id = sys.argv[3]
envelope = DurableEventEnvelope(
    event_id,
    sequence,
    "workspace.initialized",
    "2026-08-04T00:00:00.000000Z",
    None,
    {"project_name": "demo"},
)
adapter = WorkspaceEventArchiveDeliveryAdapter(root, WorkspaceEventArchive("audit"))
outcome = adapter.deliver(envelope)
print(outcome.state.value, outcome.failure_reason)
"""


def _environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path.cwd() / "src")
    return environment


def _run(root: Path, sequence: int, event_id: str) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        (sys.executable, "-c", _CHILD, str(root), str(sequence), event_id),
        env=_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_same_event_race_installs_or_verifies_one_identical_result(tmp_path: Path) -> None:
    event_id = "00000000Z80000000000000000"
    processes = [_run(tmp_path, 7, event_id) for _ in range(8)]
    results = [process.communicate(timeout=10) for process in processes]

    assert all(process.returncode == 0 for process in processes)
    assert all(stderr == b"" for _, stderr in results)
    assert all(stdout == b"delivered None\n" for stdout, _ in results)
    target = tmp_path / ".ansiblectl/events/archives/audit" / f"{7:020d}-{event_id}.json"
    expected = DurableEventEnvelope(
        event_id,
        7,
        "workspace.initialized",
        "2026-08-04T00:00:00.000000Z",
        None,
        {"project_name": "demo"},
    )
    assert target.read_bytes() == expected.to_canonical_bytes()
    assert target.stat().st_nlink == 1


def test_different_event_races_preserve_every_complete_result(tmp_path: Path) -> None:
    identities = [(index, f"00000000Z8{index:016d}") for index in range(1, 7)]
    processes = [_run(tmp_path, sequence, event_id) for sequence, event_id in identities]
    results = [process.communicate(timeout=10) for process in processes]

    assert all(process.returncode == 0 for process in processes)
    assert all(stderr == b"" for _, stderr in results)
    assert all(stdout == b"delivered None\n" for stdout, _ in results)
    archive = tmp_path / ".ansiblectl/events/archives/audit"
    final_files = sorted(path for path in archive.iterdir() if not path.name.startswith(".stage-"))
    assert len(final_files) == len(identities)
    assert all(path.stat().st_nlink == 1 for path in final_files)

"""Process-boundary and hostile-state tests for the durable event outbox."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

from ansiblectl.domain.errors import StateError
from ansiblectl.domain.events import Event
from ansiblectl.infrastructure.event_outbox import SqliteEventOutbox

_CRASH_EXIT = 86
_APPEND_CHILD = """
import os
import sys
from pathlib import Path

from ansiblectl.domain.events import Event
from ansiblectl.infrastructure.event_outbox import SqliteEventOutbox

root = Path(sys.argv[1])
selected = sys.argv[2]

def checkpoint(name: str) -> None:
    if name == selected:
        os._exit(86)

SqliteEventOutbox(root, checkpoint=checkpoint).append(
    Event("workspace.initialized", {"checkpoint": selected})
)
"""
_PARALLEL_APPEND_CHILD = """
import sys
from pathlib import Path

from ansiblectl.domain.events import Event
from ansiblectl.infrastructure.event_outbox import SqliteEventOutbox

sequence = SqliteEventOutbox(Path(sys.argv[1])).append(
    Event("workspace.initialized", {"worker": sys.argv[2]})
).sequence
print(sequence)
"""


def _environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path.cwd() / "src")
    return environment


@pytest.mark.parametrize(
    ("checkpoint", "expected_sequences"),
    [
        ("append.inserted", []),
        ("append.committed", [1]),
    ],
)
def test_real_process_termination_respects_append_commit_boundary(
    tmp_path: Path,
    checkpoint: str,
    expected_sequences: list[int],
) -> None:
    child = subprocess.run(
        (sys.executable, "-c", _APPEND_CHILD, str(tmp_path), checkpoint),
        env=_environment(),
        check=False,
        capture_output=True,
        timeout=10,
    )

    assert child.returncode == _CRASH_EXIT
    assert child.stdout == b""
    assert child.stderr == b""
    assert [event.sequence for event in SqliteEventOutbox(tmp_path).read_all()] == (
        expected_sequences
    )
    assert SqliteEventOutbox(tmp_path).append(Event("workspace.initialized", {})).sequence == (
        len(expected_sequences) + 1
    )


def test_independent_processes_allocate_contiguous_sequences(tmp_path: Path) -> None:
    processes = [
        subprocess.Popen(
            (sys.executable, "-c", _PARALLEL_APPEND_CHILD, str(tmp_path), str(index)),
            env=_environment(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for index in range(12)
    ]

    sequences: list[int] = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=15)
        assert process.returncode == 0, stderr.decode()
        assert stderr == b""
        sequences.append(int(stdout))

    assert sorted(sequences) == list(range(1, 13))
    assert [event.sequence for event in SqliteEventOutbox(tmp_path).read_all()] == list(
        range(1, 13)
    )


def test_corrupt_database_is_preserved_and_rejected(tmp_path: Path) -> None:
    directory = tmp_path / ".ansiblectl/events"
    directory.mkdir(parents=True)
    path = directory / "outbox.sqlite3"
    evidence = b"not a sqlite database\nprivate evidence"
    path.write_bytes(evidence)

    with pytest.raises(StateError, match="could not be read safely"):
        SqliteEventOutbox(tmp_path).read_all()

    assert path.read_bytes() == evidence


def test_failed_integrity_check_is_preserved_and_rejected(tmp_path: Path) -> None:
    outbox = SqliteEventOutbox(tmp_path)
    outbox.append(Event("workspace.initialized", {}))
    path = tmp_path / ".ansiblectl/events/outbox.sqlite3"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA writable_schema = ON")
        connection.execute("UPDATE sqlite_schema SET rootpage = 999999 WHERE name = 'events'")
        connection.commit()

    before = path.read_bytes()
    with pytest.raises(StateError):
        outbox.read_all()
    assert path.read_bytes() == before


@pytest.mark.parametrize("unsafe_name", [".ansiblectl", "events"])
def test_symlinked_state_directories_cannot_escape_workspace(
    tmp_path: Path, unsafe_name: str
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    if unsafe_name == ".ansiblectl":
        (tmp_path / ".ansiblectl").symlink_to(outside, target_is_directory=True)
    else:
        private = tmp_path / ".ansiblectl"
        private.mkdir()
        (private / "events").symlink_to(outside, target_is_directory=True)

    with pytest.raises(StateError, match="symbolic links"):
        SqliteEventOutbox(tmp_path).append(Event("workspace.initialized", {}))
    assert list(outside.iterdir()) == []


def test_symlinked_lock_does_not_touch_target(tmp_path: Path) -> None:
    directory = tmp_path / ".ansiblectl/events"
    directory.mkdir(parents=True)
    target = tmp_path / "outside.lock"
    target.write_bytes(b"evidence")
    (directory / "outbox.lock").symlink_to(target)

    with pytest.raises(StateError, match="lock must not be a symbolic link"):
        SqliteEventOutbox(tmp_path).append(Event("workspace.initialized", {}))

    assert target.read_bytes() == b"evidence"

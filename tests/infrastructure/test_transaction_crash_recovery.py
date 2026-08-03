"""Subprocess crash tests for durable transaction journal transitions."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from ansiblectl.domain.errors import FilesystemRecoveryError
from ansiblectl.domain.filesystem import RecoveryAction
from ansiblectl.infrastructure.transactional_filesystem import TransactionalFilesystem

_CRASH_EXIT = 86
_CHILD = """
import os
import sys
from pathlib import Path

from ansiblectl.infrastructure.transactional_filesystem import TransactionalFilesystem

root = Path(sys.argv[1])
selected = sys.argv[2]

def checkpoint(name: str) -> None:
    if selected.startswith("rollback.") and name == "commit.target_changed":
        raise OSError("enter automatic rollback")
    if name == selected:
        os._exit(86)

transaction = TransactionalFilesystem(root, checkpoint=checkpoint).begin()
transaction.stage_write(Path("target"), b"after")
transaction.commit()
"""


@pytest.mark.parametrize(
    ("checkpoint", "action", "content_after_crash", "content_after_recovery"),
    [
        ("stage.content_synced", RecoveryAction.ROLLBACK, b"before", b"before"),
        ("stage.journal_synced", RecoveryAction.ROLLBACK, b"before", b"before"),
        ("commit.state_synced", RecoveryAction.ROLLBACK, b"before", b"before"),
        ("commit.backup_synced", RecoveryAction.ROLLBACK, b"before", b"before"),
        ("commit.intent_synced", RecoveryAction.ROLLBACK, b"before", b"before"),
        ("commit.target_changed", RecoveryAction.ROLLBACK, b"after", b"before"),
        ("commit.target_synced", RecoveryAction.ROLLBACK, b"after", b"before"),
        ("commit.committed_synced", RecoveryAction.CLEANUP, b"after", b"after"),
        ("rollback.backup_restored", RecoveryAction.ROLLBACK, b"before", b"before"),
        ("rollback.complete_synced", RecoveryAction.CLEANUP, b"before", b"before"),
    ],
)
def test_new_process_recovers_after_real_process_termination(
    tmp_path: Path,
    checkpoint: str,
    action: RecoveryAction,
    content_after_crash: bytes,
    content_after_recovery: bytes,
) -> None:
    (tmp_path / "target").write_bytes(b"before")
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path.cwd() / "src")

    child = subprocess.run(
        (sys.executable, "-c", _CHILD, str(tmp_path), checkpoint),
        env=environment,
        check=False,
        capture_output=True,
        timeout=10,
    )

    assert child.returncode == _CRASH_EXIT
    assert child.stdout == b""
    assert child.stderr == b""
    assert (tmp_path / "target").read_bytes() == content_after_crash
    filesystem = TransactionalFilesystem(tmp_path)
    diagnostics = filesystem.diagnostics()
    assert len(diagnostics) == 1
    assert diagnostics[0].active_owner is False
    assert diagnostics[0].action is action

    filesystem.recover()

    assert (tmp_path / "target").read_bytes() == content_after_recovery
    assert filesystem.diagnostics() == ()
    assert filesystem.recover().rolled_back == ()


def test_crash_before_first_journal_requires_manual_inspection(tmp_path: Path) -> None:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path.cwd() / "src")

    child = subprocess.run(
        (
            sys.executable,
            "-c",
            _CHILD,
            str(tmp_path),
            "transaction.directory_created",
        ),
        env=environment,
        check=False,
        capture_output=True,
        timeout=10,
    )

    assert child.returncode == _CRASH_EXIT
    filesystem = TransactionalFilesystem(tmp_path)
    diagnostic = filesystem.diagnostics()[0]
    assert diagnostic.action is RecoveryAction.MANUAL_INSPECTION
    with pytest.raises(FilesystemRecoveryError, match="unreadable"):
        filesystem.recover()
    assert filesystem.diagnostics()[0].action is RecoveryAction.MANUAL_INSPECTION

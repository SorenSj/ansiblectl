"""Multiprocess contention tests for transactional filesystem ownership."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from ansiblectl.domain.filesystem import RecoveryAction, RecoveryReason
from ansiblectl.infrastructure.transactional_filesystem import TransactionalFilesystem

_TIMEOUT = 10.0
_COMMIT_CHILD = """
import sys
import time
from pathlib import Path

from ansiblectl.infrastructure.transactional_filesystem import TransactionalFilesystem

root, target, value, ready, gate = map(Path, sys.argv[1:])
transaction = TransactionalFilesystem(root).begin()
transaction.stage_write(target, str(value).encode())
ready.touch()
deadline = time.monotonic() + 10
while not gate.exists():
    if time.monotonic() >= deadline:
        raise TimeoutError("commit gate was not released")
    time.sleep(0.01)
transaction.commit()
"""
_RECOVERY_CHILD = """
import sys
from pathlib import Path

from ansiblectl.infrastructure.transactional_filesystem import TransactionalFilesystem

result = TransactionalFilesystem(Path(sys.argv[1])).recover()
print(len(result.rolled_back))
"""


def _environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path.cwd() / "src")
    return environment


def _wait_for(*paths: Path) -> None:
    deadline = time.monotonic() + _TIMEOUT
    while not all(path.exists() for path in paths):
        if time.monotonic() >= deadline:
            raise AssertionError("child processes did not reach the contention checkpoint")
        time.sleep(0.01)


def _start_commit(
    root: Path, target: str, value: str, ready: Path, gate: Path
) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        (sys.executable, "-c", _COMMIT_CHILD, str(root), target, value, str(ready), str(gate)),
        env=_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _finish(process: subprocess.Popen[bytes]) -> None:
    stdout, stderr = process.communicate(timeout=_TIMEOUT)
    assert process.returncode == 0, stderr.decode()
    assert stdout == b""
    assert stderr == b""


def test_two_processes_commit_different_targets_without_lost_work(tmp_path: Path) -> None:
    gate = tmp_path / "commit.gate"
    first_ready = tmp_path / "first.ready"
    second_ready = tmp_path / "second.ready"
    first = _start_commit(tmp_path, "first", "one", first_ready, gate)
    second = _start_commit(tmp_path, "second", "two", second_ready, gate)

    _wait_for(first_ready, second_ready)
    gate.touch()
    _finish(first)
    _finish(second)

    assert (tmp_path / "first").read_text(encoding="utf-8") == "one"
    assert (tmp_path / "second").read_text(encoding="utf-8") == "two"
    assert TransactionalFilesystem(tmp_path).diagnostics() == ()


def test_two_processes_committing_same_target_leave_one_complete_value(tmp_path: Path) -> None:
    (tmp_path / "shared").write_text("before", encoding="utf-8")
    gate = tmp_path / "commit.gate"
    first_ready = tmp_path / "first.ready"
    second_ready = tmp_path / "second.ready"
    first = _start_commit(tmp_path, "shared", "one", first_ready, gate)
    second = _start_commit(tmp_path, "shared", "two", second_ready, gate)

    _wait_for(first_ready, second_ready)
    gate.touch()
    _finish(first)
    _finish(second)

    assert (tmp_path / "shared").read_text(encoding="utf-8") in {"one", "two"}
    assert TransactionalFilesystem(tmp_path).diagnostics() == ()


def test_preview_and_recovery_do_not_mutate_live_owned_transaction(tmp_path: Path) -> None:
    gate = tmp_path / "commit.gate"
    ready = tmp_path / "owner.ready"
    child = _start_commit(tmp_path, "owned", "value", ready, gate)

    _wait_for(ready)
    filesystem = TransactionalFilesystem(tmp_path)
    diagnostics = filesystem.diagnostics()
    assert len(diagnostics) == 1
    assert diagnostics[0].active_owner is True
    assert diagnostics[0].action is RecoveryAction.NONE
    assert diagnostics[0].reasons[0] is RecoveryReason.ACTIVE_OWNER
    assert filesystem.pending() == ()
    assert filesystem.recover().rolled_back == ()

    gate.touch()
    _finish(child)
    assert (tmp_path / "owned").read_text(encoding="utf-8") == "value"
    assert filesystem.diagnostics() == ()


def test_two_recovery_processes_serialize_without_double_rollback(tmp_path: Path) -> None:
    filesystem = TransactionalFilesystem(tmp_path)
    for name in ("first", "second"):
        target = tmp_path / name
        target.write_text("before", encoding="utf-8")
        transaction = filesystem.begin()
        transaction.stage_write(Path(name), b"after")
        transaction._persist("committing")
        transaction._apply(0, transaction.operations[0])
        transaction._persist("committing")
        transaction._release_active()

    processes = [
        subprocess.Popen(
            (sys.executable, "-c", _RECOVERY_CHILD, str(tmp_path)),
            env=_environment(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(2)
    ]
    results = [process.communicate(timeout=_TIMEOUT) for process in processes]

    assert all(process.returncode == 0 for process in processes)
    assert all(stderr == b"" for _, stderr in results)
    assert sorted(stdout.strip() for stdout, _ in results) == [b"0", b"2"]
    assert (tmp_path / "first").read_text(encoding="utf-8") == "before"
    assert (tmp_path / "second").read_text(encoding="utf-8") == "before"
    assert filesystem.diagnostics() == ()

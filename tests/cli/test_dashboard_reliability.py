"""Real subprocess reliability tests for the dashboard terminal lifecycle."""

from __future__ import annotations

import fcntl
import os
import pty
import select
import signal
import struct
import sys
import termios
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

import pytest

from ansiblectl.cli.composition import build_workspace_service
from ansiblectl.domain.errors import ExitCode


@dataclass
class DashboardProcess:
    child: int
    master: int
    slave: int
    slave_name: str
    original_attributes: list[int | list[bytes]]
    output: bytearray


def _set_size(descriptor: int, *, columns: int, rows: int) -> None:
    fcntl.ioctl(descriptor, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))


def _launch(workspace: Path) -> DashboardProcess:
    master, slave = pty.openpty()
    slave_name = os.ttyname(slave)
    _set_size(master, columns=100, rows=30)
    original_attributes = termios.tcgetattr(slave)
    child = os.fork()
    if child == 0:
        os.close(master)
        os.setsid()
        fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
        os.tcsetpgrp(slave, os.getpgrp())
        for descriptor in (0, 1, 2):
            os.dup2(slave, descriptor)
        if slave > 2:
            os.close(slave)
        repository_root = Path(__file__).resolve().parents[2]
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(repository_root / "src")
        arguments = [
            sys.executable,
            "-c",
            "from ansiblectl.cli.main import cli; raise SystemExit(cli())",
            "--workspace",
            str(workspace),
            "dashboard",
        ]
        os.execve(sys.executable, arguments, environment)
    return DashboardProcess(child, master, slave, slave_name, original_attributes, bytearray())


def _read_until(process: DashboardProcess, marker: bytes, *, seconds: float = 10) -> bytes:
    output = bytearray()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        readable, _, _ = select.select([process.master], [], [], 0.1)
        if readable:
            chunk = os.read(process.master, 65536)
            if not chunk:
                break
            output.extend(chunk)
            process.output.extend(chunk)
            if marker in output:
                return bytes(output)
        selected, status = os.waitpid(process.child, os.WNOHANG)
        if selected == process.child:
            pytest.fail(
                f"Dashboard exited before expected terminal marker with status "
                f"{os.waitstatus_to_exitcode(status)}."
            )
    pytest.fail("Dashboard did not emit the expected terminal marker within its test bound.")


def _wait(process: DashboardProcess, *, seconds: float = 10) -> int:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _drain(process)
        selected, status = os.waitpid(process.child, os.WNOHANG)
        if selected == process.child:
            return status
        time.sleep(0.01)
    os.killpg(process.child, signal.SIGKILL)
    kill_deadline = time.monotonic() + 2
    while time.monotonic() < kill_deadline:
        selected, _ = os.waitpid(process.child, os.WNOHANG)
        if selected == process.child:
            break
        time.sleep(0.01)
    pytest.fail("Dashboard subprocess did not exit within its test bound.")


def _drain(process: DashboardProcess) -> bytes:
    output = bytearray()
    while select.select([process.master], [], [], 0)[0]:
        chunk = os.read(process.master, 65536)
        if not chunk:
            break
        output.extend(chunk)
    process.output.extend(output)
    return bytes(output)


def _close(process: DashboardProcess) -> None:
    for descriptor in (process.master, process.slave):
        with suppress(OSError):
            os.close(descriptor)


def _restored_attributes(process: DashboardProcess) -> list[int | list[bytes]]:
    descriptor = os.open(process.slave_name, os.O_RDWR | os.O_NOCTTY)
    try:
        return termios.tcgetattr(descriptor)
    finally:
        os.close(descriptor)


@pytest.mark.parametrize("interrupt", [signal.SIGINT, signal.SIGTERM])
def test_real_interrupt_restores_terminal_and_returns_130(
    tmp_path: Path, interrupt: signal.Signals
) -> None:
    workspace = tmp_path / "workspace"
    build_workspace_service().initialize(workspace)
    process = _launch(workspace)
    try:
        _read_until(process, b"Consumers")
        os.killpg(process.child, interrupt)
        status = _wait(process)
        _drain(process)
        output = bytes(process.output)

        assert os.waitstatus_to_exitcode(status) == ExitCode.INTERRUPTED
        assert _restored_attributes(process) == process.original_attributes
        assert b"\x1b[?1049h\x1b[?25l" in output
        assert b"\x1b[?25h\x1b[?1049l" in output
        assert os.fsencode(workspace) not in output
    finally:
        _close(process)


def test_real_resize_repaints_without_input_or_snapshot_disclosure(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    build_workspace_service().initialize(workspace)
    process = _launch(workspace)
    try:
        _read_until(process, b"Consumers")

        _set_size(process.master, columns=79, rows=23)
        small = _read_until(process, b"Terminal must be at least 80 columns by 24 rows.")
        assert b"Ansiblectl is ready" not in small
        assert os.fsencode(workspace) not in small

        _set_size(process.master, columns=100, rows=30)
        restored = _read_until(process, b"Consumers")
        assert b"Status" in restored
        assert b"Executions" in restored

        os.write(process.master, b"q")
        status = _wait(process)
        assert os.waitstatus_to_exitcode(status) == ExitCode.SUCCESS
        assert _restored_attributes(process) == process.original_attributes
    finally:
        _close(process)

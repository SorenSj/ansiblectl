"""Public dashboard command boundary tests."""

from __future__ import annotations

import errno
import fcntl
import json
import os
import pty
import select
import struct
import sys
import termios
import time
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

import pytest

from ansiblectl.application.dashboard import (
    DashboardCount,
    DashboardSnapshot,
)
from ansiblectl.cli.composition import build_workspace_service
from ansiblectl.cli.dashboard_rendering import DashboardViewState
from ansiblectl.cli.dashboard_terminal import DashboardLoopResult
from ansiblectl.cli.main import build_parser, cli, main
from ansiblectl.domain.errors import ErrorCode, ExitCode, UsageError
from ansiblectl.domain.workspace import Workspace


def _snapshot() -> DashboardSnapshot:
    return DashboardSnapshot(
        "0.17.0",
        "ready",
        0,
        (
            DashboardCount("completed", 0),
            DashboardCount("failed", 0),
            DashboardCount("timed_out", 0),
            DashboardCount("cancelled", 0),
        ),
        (DashboardCount("check", 0), DashboardCount("apply", 0)),
        (),
        (),
    )


@dataclass
class DescriptorStream:
    descriptor: int

    def fileno(self) -> int:
        return self.descriptor


class WorkspaceService:
    def __init__(self, calls: list[str], root: Path) -> None:
        self.calls = calls
        self.root = root

    def resolve(self, explicit_path: Path | None, current_directory: Path) -> Workspace:
        self.calls.append("workspace")
        assert explicit_path == self.root
        return Workspace(self.root, self.root / ".ansiblectl/workspace.json", 1)


class SnapshotService:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.value = _snapshot()

    def snapshot(self) -> DashboardSnapshot:
        self.calls.append("snapshot")
        return self.value


def test_dashboard_resolves_explicit_workspace_and_snapshot_before_terminal(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    snapshots = SnapshotService(calls)

    class Session:
        def run(self, snapshot: DashboardSnapshot) -> DashboardLoopResult:
            calls.append("run")
            assert snapshot is _snapshot_value
            return DashboardLoopResult(ExitCode.SUCCESS, DashboardViewState())

    _snapshot_value = snapshots.value

    def factory(stdin_fd: int, stdout_fd: int, selected_snapshots: SnapshotService) -> Session:
        calls.append("session")
        assert (stdin_fd, stdout_fd) == (10, 11)
        assert selected_snapshots is snapshots
        return Session()

    result = main(
        ["--workspace", str(tmp_path), "dashboard"],
        workspace_service=WorkspaceService(calls, tmp_path),  # type: ignore[arg-type]
        dashboard_snapshot_service=snapshots,  # type: ignore[arg-type]
        dashboard_session_factory=factory,  # type: ignore[arg-type]
        stdin=DescriptorStream(10),  # type: ignore[arg-type]
        stdout=DescriptorStream(11),  # type: ignore[arg-type]
    )

    assert result == ExitCode.SUCCESS
    assert calls == ["workspace", "snapshot", "session", "run"]


@pytest.mark.parametrize(
    "arguments",
    [
        ["dashboard"],
        ["--workspace", ".", "--output", "json", "dashboard"],
        ["--workspace", ".", "--output", "yaml", "dashboard"],
        ["--workspace", ".", "--non-interactive", "dashboard"],
    ],
)
def test_dashboard_rejects_unbounded_context_before_services(arguments: list[str]) -> None:
    with pytest.raises(UsageError):
        main(arguments, propagate_errors=True)


def test_dashboard_redirect_fails_without_terminal_sequences(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    assert cli(["workspace", "init", str(workspace)], stdout=StringIO()) == 0
    stdout, stderr = StringIO(), StringIO()

    result = cli(
        ["--workspace", str(workspace), "dashboard"],
        stdin=StringIO(),
        stdout=stdout,
        stderr=stderr,
    )

    rendered = stdout.getvalue() + stderr.getvalue()
    assert result == ExitCode.GENERAL_ERROR
    assert stdout.getvalue() == ""
    assert "supported foreground terminal" in stderr.getvalue()
    assert "\x1b" not in rendered


@pytest.mark.parametrize("output_format", ["json", "yaml"])
def test_dashboard_machine_output_is_structured_usage_error(output_format: str) -> None:
    stdout, stderr = StringIO(), StringIO()

    result = cli(["--output", output_format, "dashboard"], stdout=stdout, stderr=stderr)

    payload = json.loads(stdout.getvalue()) if output_format == "json" else None
    assert result == ExitCode.USAGE_ERROR
    assert stderr.getvalue() == ""
    if payload is not None:
        assert payload["error"]["code"] == ErrorCode.USAGE_ERROR
    else:
        import yaml

        assert yaml.safe_load(stdout.getvalue())["error"]["code"] == ErrorCode.USAGE_ERROR
    assert "\x1b" not in stdout.getvalue()


def test_dashboard_is_listed_as_one_value_free_command_token() -> None:
    parser = build_parser()

    assert parser.parse_args(["--workspace", ".", "dashboard"]).command == "dashboard"


def test_installed_boundary_runs_dashboard_in_real_foreground_pty(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    build_workspace_service().initialize(workspace)
    child, master = pty.fork()
    if child == 0:
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

    output = bytearray()
    status: int | None = None
    try:
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0))
        deadline = time.monotonic() + 10
        sent_quit = False
        while time.monotonic() < deadline:
            readable, _, _ = select.select([master], [], [], 0.1)
            if readable:
                try:
                    chunk = os.read(master, 65536)
                except OSError as error:
                    if error.errno != errno.EIO:
                        raise
                    chunk = b""
                output.extend(chunk)
                if b"ansiblectl dashboard" in output and not sent_quit:
                    os.write(master, b"q")
                    sent_quit = True
            selected, candidate = os.waitpid(child, os.WNOHANG)
            if selected == child:
                status = candidate
                break
        if status is None:
            os.kill(child, 15)
            _, status = os.waitpid(child, 0)
            pytest.fail("Dashboard subprocess did not exit within its test bound.")
    finally:
        os.close(master)

    assert os.waitstatus_to_exitcode(status) == ExitCode.SUCCESS
    assert b"\x1b[?1049h\x1b[?25l" in output
    assert b"\x1b[?25h\x1b[?1049l" in output
    assert b"Status" in output
    assert b"Executions" in output
    assert b"Consumers" in output
    assert os.fsencode(workspace) not in output

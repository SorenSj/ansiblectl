"""Dashboard input and terminal lifecycle tests."""

from __future__ import annotations

import os
import pty
import termios
import tty
from dataclasses import replace

import pytest

import ansiblectl.cli.dashboard_terminal as terminal_module
from ansiblectl.application.dashboard import (
    DashboardConsumerRow,
    DashboardCount,
    DashboardExecutionRow,
    DashboardQueries,
    DashboardSnapshot,
    DashboardSnapshotError,
    DashboardSnapshotService,
)
from ansiblectl.cli.dashboard_rendering import DashboardPanel, DashboardViewState
from ansiblectl.cli.dashboard_terminal import (
    DashboardAction,
    DashboardTerminalError,
    DashboardTerminalSession,
    apply_dashboard_action,
    parse_dashboard_input,
)
from ansiblectl.domain.errors import ExitCode


def _snapshot() -> DashboardSnapshot:
    executions = tuple(
        DashboardExecutionRow("time", f"run-{index}", "completed", "run", "check", 0, 1.0)
        for index in range(3)
    )
    consumers = tuple(
        DashboardConsumerRow(f"sink-{index}", 1, 0, None, 0, None, "idle") for index in range(2)
    )
    return DashboardSnapshot(
        "0.17.0",
        "ready",
        3,
        (
            DashboardCount("completed", 3),
            DashboardCount("failed", 0),
            DashboardCount("timed_out", 0),
            DashboardCount("cancelled", 0),
        ),
        (DashboardCount("check", 3), DashboardCount("apply", 0)),
        executions,
        consumers,
    )


def _unused_snapshots() -> DashboardSnapshotService:
    def forbidden() -> object:
        raise AssertionError("snapshot query called")

    return DashboardSnapshotService(
        DashboardQueries(forbidden, forbidden, forbidden, forbidden)  # type: ignore[arg-type]
    )


@pytest.mark.parametrize(
    ("data", "action"),
    [
        (b"", DashboardAction.QUIT),
        (b"q", DashboardAction.QUIT),
        (b"\x1b", DashboardAction.QUIT),
        (b"r", DashboardAction.REFRESH),
        (b"\t", DashboardAction.NEXT_PANEL),
        (b"\x1b[C", DashboardAction.NEXT_PANEL),
        (b"\x1b[Z", DashboardAction.PREVIOUS_PANEL),
        (b"\x1b[D", DashboardAction.PREVIOUS_PANEL),
        (b"j", DashboardAction.NEXT_ROW),
        (b"\x1b[B", DashboardAction.NEXT_ROW),
        (b"k", DashboardAction.PREVIOUS_ROW),
        (b"\x1b[A", DashboardAction.PREVIOUS_ROW),
        (b"x", DashboardAction.IGNORE),
        (b"command text", DashboardAction.IGNORE),
        (b"\x1b[", DashboardAction.IGNORE),
        (b"x" * 33, DashboardAction.IGNORE),
    ],
)
def test_input_vocabulary_is_exact(data: bytes, action: DashboardAction) -> None:
    assert parse_dashboard_input(data) is action


def test_navigation_wraps_panels_and_clamps_rows() -> None:
    snapshot = _snapshot()
    state = DashboardViewState()

    state = apply_dashboard_action(state, snapshot, DashboardAction.PREVIOUS_PANEL)
    assert state.panel is DashboardPanel.CONSUMERS
    state = apply_dashboard_action(state, snapshot, DashboardAction.NEXT_ROW)
    state = apply_dashboard_action(state, snapshot, DashboardAction.NEXT_ROW)
    assert state.consumer_index == 1
    state = apply_dashboard_action(state, snapshot, DashboardAction.PREVIOUS_ROW)
    assert state.consumer_index == 0
    state = replace(state, panel=DashboardPanel.EXECUTIONS)
    for _ in range(5):
        state = apply_dashboard_action(state, snapshot, DashboardAction.NEXT_ROW)
    assert state.execution_index == 2
    assert apply_dashboard_action(state, snapshot, DashboardAction.IGNORE) is state


def test_preflight_rejects_redirected_streams_without_terminal_mutation(tmp_path: object) -> None:
    read_fd, write_fd = os.pipe()
    try:
        session = DashboardTerminalSession(read_fd, write_fd, _unused_snapshots())
        with pytest.raises(DashboardTerminalError, match="foreground terminal"):
            session.preflight()
        session.restore()
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_pseudo_terminal_quit_restores_attributes_and_modes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    master, slave = pty.openpty()
    monkeypatch.setattr(os, "tcgetpgrp", lambda _fd: os.getpgrp())
    before = termios.tcgetattr(slave)
    frames: list[tuple[int, int]] = []
    writes: list[bytes] = []
    original_write_all = terminal_module._write_all

    def observe_write(file_descriptor: int, data: bytes) -> None:
        writes.append(data)
        original_write_all(file_descriptor, data)

    monkeypatch.setattr(terminal_module, "_write_all", observe_write)

    def renderer(
        _snapshot_value: DashboardSnapshot,
        _state: DashboardViewState,
        *,
        columns: int,
        rows: int,
    ) -> str:
        frames.append((columns, rows))
        os.write(master, b"q")
        return "frame"

    try:
        session = DashboardTerminalSession(slave, slave, _unused_snapshots(), renderer=renderer)
        result = session.run(_snapshot())

        assert result.exit_code is ExitCode.SUCCESS
        assert frames
        assert termios.tcgetattr(slave) == before
        assert b"\x1b[?1049h\x1b[?25l" in writes
        assert b"\x1b[?25h\x1b[?1049l" in writes
        session.restore()
        assert termios.tcgetattr(slave) == before
    finally:
        os.close(master)
        os.close(slave)


def test_refresh_failure_retains_snapshot_and_sets_value_free_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    master, slave = pty.openpty()
    monkeypatch.setattr(os, "tcgetpgrp", lambda _fd: os.getpgrp())
    rendered_states: list[DashboardViewState] = []

    class FailingSnapshots:
        def snapshot(self) -> DashboardSnapshot:
            raise DashboardSnapshotError("Dashboard snapshot is unavailable.")

    def renderer(
        _snapshot_value: DashboardSnapshot,
        state: DashboardViewState,
        *,
        columns: int,
        rows: int,
    ) -> str:
        rendered_states.append(state)
        os.write(master, b"r" if len(rendered_states) == 1 else b"q")
        return "frame"

    try:
        session = DashboardTerminalSession(
            slave,
            slave,
            FailingSnapshots(),  # type: ignore[arg-type]
            renderer=renderer,
        )
        result = session.run(_snapshot())

        assert result.exit_code is ExitCode.SUCCESS
        assert any(state.refresh_failed for state in rendered_states)
    finally:
        os.close(master)
        os.close(slave)


def test_keyboard_interrupt_after_entry_restores_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    master, slave = pty.openpty()
    monkeypatch.setattr(os, "tcgetpgrp", lambda _fd: os.getpgrp())
    before = termios.tcgetattr(slave)

    def interrupt(
        _snapshot_value: DashboardSnapshot,
        _state: DashboardViewState,
        *,
        columns: int,
        rows: int,
    ) -> str:
        raise KeyboardInterrupt

    try:
        session = DashboardTerminalSession(slave, slave, _unused_snapshots(), renderer=interrupt)
        result = session.run(_snapshot())

        assert result.exit_code is ExitCode.INTERRUPTED
        assert termios.tcgetattr(slave) == before
    finally:
        os.close(master)
        os.close(slave)


def test_partial_raw_mode_failure_is_restored(monkeypatch: pytest.MonkeyPatch) -> None:
    master, slave = pty.openpty()
    monkeypatch.setattr(os, "tcgetpgrp", lambda _fd: os.getpgrp())
    before = termios.tcgetattr(slave)
    original_setraw = tty.setraw

    def fail_after_raw(file_descriptor: int, *, when: int) -> None:
        original_setraw(file_descriptor, when=when)
        raise OSError("forbidden-raw-failure")

    monkeypatch.setattr(tty, "setraw", fail_after_raw)
    try:
        session = DashboardTerminalSession(slave, slave, _unused_snapshots())
        with pytest.raises(DashboardTerminalError) as raised:
            session.run(_snapshot())

        assert str(raised.value) == "Dashboard terminal session failed safely."
        assert "forbidden-raw-failure" not in repr(raised.value)
        assert termios.tcgetattr(slave) == before
    finally:
        os.close(master)
        os.close(slave)

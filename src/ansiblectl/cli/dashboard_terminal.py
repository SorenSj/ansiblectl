"""Foreground POSIX terminal lifecycle for the local dashboard."""

from __future__ import annotations

import atexit
import os
import select
import signal
import termios
import threading
import tty
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum
from types import FrameType

from ansiblectl.application.dashboard import (
    DashboardSnapshot,
    DashboardSnapshotError,
    DashboardSnapshotService,
)
from ansiblectl.cli.dashboard_rendering import (
    DashboardPanel,
    DashboardViewState,
    render_dashboard,
)
from ansiblectl.domain.errors import AnsiblectlError, ExitCode

MAX_DASHBOARD_INPUT_BYTES = 32
_ENTER_TERMINAL = b"\x1b[?1049h\x1b[?25l"
_RESET_FRAME = b"\x1b[H\x1b[2J"
_LEAVE_TERMINAL = b"\x1b[?25h\x1b[?1049l"


class DashboardTerminalError(AnsiblectlError):
    """A stable value-free terminal capability or lifecycle failure."""


class DashboardAction(Enum):
    """Closed dashboard input vocabulary."""

    QUIT = "quit"
    REFRESH = "refresh"
    NEXT_PANEL = "next_panel"
    PREVIOUS_PANEL = "previous_panel"
    NEXT_ROW = "next_row"
    PREVIOUS_ROW = "previous_row"
    IGNORE = "ignore"


@dataclass(frozen=True)
class DashboardLoopResult:
    """Terminal loop outcome with the stable process exit code."""

    exit_code: ExitCode
    state: DashboardViewState


def parse_dashboard_input(data: bytes) -> DashboardAction:
    """Classify one bounded complete input read without interpreting free-form data."""

    if not isinstance(data, bytes) or len(data) > MAX_DASHBOARD_INPUT_BYTES:
        return DashboardAction.IGNORE
    return {
        b"": DashboardAction.QUIT,
        b"q": DashboardAction.QUIT,
        b"\x1b": DashboardAction.QUIT,
        b"r": DashboardAction.REFRESH,
        b"\t": DashboardAction.NEXT_PANEL,
        b"\x1b[C": DashboardAction.NEXT_PANEL,
        b"\x1b[Z": DashboardAction.PREVIOUS_PANEL,
        b"\x1b[D": DashboardAction.PREVIOUS_PANEL,
        b"j": DashboardAction.NEXT_ROW,
        b"\x1b[B": DashboardAction.NEXT_ROW,
        b"k": DashboardAction.PREVIOUS_ROW,
        b"\x1b[A": DashboardAction.PREVIOUS_ROW,
    }.get(data, DashboardAction.IGNORE)


def apply_dashboard_action(
    state: DashboardViewState,
    snapshot: DashboardSnapshot,
    action: DashboardAction,
) -> DashboardViewState:
    """Apply one non-mutating navigation action to presentation state."""

    if action is DashboardAction.NEXT_PANEL:
        return replace(state, panel=DashboardPanel((state.panel + 1) % len(DashboardPanel)))
    if action is DashboardAction.PREVIOUS_PANEL:
        return replace(state, panel=DashboardPanel((state.panel - 1) % len(DashboardPanel)))
    if action not in {DashboardAction.NEXT_ROW, DashboardAction.PREVIOUS_ROW}:
        return state
    delta = 1 if action is DashboardAction.NEXT_ROW else -1
    if state.panel is DashboardPanel.EXECUTIONS:
        maximum = max(0, len(snapshot.executions) - 1)
        return replace(state, execution_index=min(maximum, max(0, state.execution_index + delta)))
    if state.panel is DashboardPanel.CONSUMERS:
        maximum = max(0, len(snapshot.consumers) - 1)
        return replace(state, consumer_index=min(maximum, max(0, state.consumer_index + delta)))
    return state


class DashboardTerminalSession:
    """Own one foreground terminal session and restore it exactly once."""

    def __init__(
        self,
        stdin_fd: int,
        stdout_fd: int,
        snapshots: DashboardSnapshotService,
        *,
        renderer: Callable[..., str] = render_dashboard,
    ) -> None:
        self._stdin_fd = stdin_fd
        self._stdout_fd = stdout_fd
        self._snapshots = snapshots
        self._renderer = renderer
        self._original_attributes: list[int | list[bytes]] | None = None
        self._original_handlers: dict[
            int, Callable[[int, FrameType | None], object] | int | None
        ] = {}
        self._active = False
        self._registered = False
        self._interrupt_pending = False
        self._resize_pending = False
        self._wake_read_fd: int | None = None
        self._wake_write_fd: int | None = None

    def preflight(self) -> None:
        """Validate terminal and signal capabilities without mutating process state."""

        try:
            if threading.current_thread() is not threading.main_thread():
                raise OSError
            if not os.isatty(self._stdin_fd) or not os.isatty(self._stdout_fd):
                raise OSError
            input_stat = os.fstat(self._stdin_fd)
            output_stat = os.fstat(self._stdout_fd)
            if input_stat.st_rdev != output_stat.st_rdev:
                raise OSError
            process_group = os.getpgrp()
            if (
                os.tcgetpgrp(self._stdin_fd) != process_group
                or os.tcgetpgrp(self._stdout_fd) != process_group
            ):
                raise OSError
            if not all(hasattr(signal, name) for name in ("SIGINT", "SIGTERM", "SIGWINCH")):
                raise OSError
            attributes = termios.tcgetattr(self._stdin_fd)
            os.get_terminal_size(self._stdout_fd)
        except (OSError, termios.error) as error:
            raise DashboardTerminalError(
                "Dashboard requires one supported foreground terminal.", cause=error
            ) from error
        self._original_attributes = attributes

    def run(
        self,
        initial_snapshot: DashboardSnapshot,
        initial_state: DashboardViewState | None = None,
    ) -> DashboardLoopResult:
        """Enter, own, and restore one dashboard terminal session."""

        self.preflight()
        state = initial_state or DashboardViewState()
        snapshot = initial_snapshot
        self._install_restoration()
        self._active = True
        try:
            tty.setraw(self._stdin_fd, when=termios.TCSANOW)
            _write_all(self._stdout_fd, _ENTER_TERMINAL)
            while True:
                self._render(snapshot, state)
                if self._wake_read_fd is None:
                    raise OSError("Dashboard resize wakeup is unavailable.")
                readable, _, _ = select.select([self._stdin_fd, self._wake_read_fd], [], [])
                if self._wake_read_fd in readable:
                    with _suppress_terminal_errors():
                        os.read(self._wake_read_fd, MAX_DASHBOARD_INPUT_BYTES)
                    if self._interrupt_pending:
                        return DashboardLoopResult(ExitCode.INTERRUPTED, state)
                    continue
                action = parse_dashboard_input(os.read(self._stdin_fd, MAX_DASHBOARD_INPUT_BYTES))
                if action is DashboardAction.QUIT:
                    return DashboardLoopResult(ExitCode.SUCCESS, state)
                if action is DashboardAction.REFRESH:
                    try:
                        snapshot = self._snapshots.snapshot()
                        state = replace(state, refresh_failed=False)
                    except DashboardSnapshotError:
                        state = replace(state, refresh_failed=True)
                else:
                    state = apply_dashboard_action(state, snapshot, action)
        except KeyboardInterrupt:
            return DashboardLoopResult(ExitCode.INTERRUPTED, state)
        except (OSError, termios.error, ValueError) as error:
            raise DashboardTerminalError(
                "Dashboard terminal session failed safely.", cause=error
            ) from error
        finally:
            self.restore()

    def restore(self) -> None:
        """Idempotently restore attributes, modes, handlers, and cleanup registration."""

        if not self._active and not self._registered and not self._original_handlers:
            return
        active = self._active
        self._active = False
        try:
            if active and self._original_attributes is not None:
                with _suppress_terminal_errors():
                    termios.tcsetattr(self._stdin_fd, termios.TCSANOW, self._original_attributes)
                    termios.tcflush(self._stdin_fd, termios.TCIFLUSH)
                with _suppress_terminal_errors():
                    _write_all(self._stdout_fd, _LEAVE_TERMINAL)
        finally:
            for number, handler in self._original_handlers.items():
                with _suppress_terminal_errors():
                    signal.signal(number, handler)
            self._original_handlers.clear()
            for descriptor_name in ("_wake_read_fd", "_wake_write_fd"):
                descriptor = getattr(self, descriptor_name)
                if descriptor is not None:
                    with _suppress_terminal_errors():
                        os.close(descriptor)
                    setattr(self, descriptor_name, None)
            if self._registered:
                atexit.unregister(self.restore)
                self._registered = False

    def _install_restoration(self) -> None:
        if self._original_attributes is None:
            raise DashboardTerminalError("Dashboard terminal preflight is incomplete.")
        handlers: dict[int, Callable[[int, FrameType | None], None]] = {
            signal.SIGINT: self._interrupt,
            signal.SIGTERM: self._interrupt,
            signal.SIGWINCH: self._resize,
        }
        try:
            self._wake_read_fd, self._wake_write_fd = os.pipe()
            os.set_blocking(self._wake_read_fd, False)
            os.set_blocking(self._wake_write_fd, False)
            for number, handler in handlers.items():
                self._original_handlers[number] = signal.getsignal(number)
                signal.signal(number, handler)
            atexit.register(self.restore)
            self._registered = True
        except (OSError, ValueError) as error:
            self.restore()
            raise DashboardTerminalError(
                "Dashboard terminal signal setup is unavailable.", cause=error
            ) from error

    def _interrupt(self, _number: int, _frame: FrameType | None) -> None:
        self._interrupt_pending = True
        if self._wake_write_fd is not None:
            with _suppress_terminal_errors():
                os.write(self._wake_write_fd, b"i")

    def _resize(self, _number: int, _frame: FrameType | None) -> None:
        self._resize_pending = True
        if self._wake_write_fd is not None:
            with _suppress_terminal_errors():
                os.write(self._wake_write_fd, b"r")

    def _render(self, snapshot: DashboardSnapshot, state: DashboardViewState) -> None:
        size = os.get_terminal_size(self._stdout_fd)
        frame = self._renderer(snapshot, state, columns=size.columns, rows=size.lines)
        _write_all(self._stdout_fd, _RESET_FRAME + frame.encode("ascii"))
        self._resize_pending = False


class _suppress_terminal_errors:
    """Suppress cleanup-only failures without masking the primary outcome."""

    def __enter__(self) -> None:
        return None

    def __exit__(
        self,
        _error_type: type[BaseException] | None,
        _error: BaseException | None,
        _traceback: object,
    ) -> bool:
        return True


def _write_all(file_descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(file_descriptor, view)
        if written <= 0:
            raise OSError("Terminal write did not make progress.")
        view = view[written:]


__all__ = [
    "DashboardAction",
    "DashboardLoopResult",
    "DashboardTerminalError",
    "DashboardTerminalSession",
    "MAX_DASHBOARD_INPUT_BYTES",
    "apply_dashboard_action",
    "parse_dashboard_input",
]

"""Deterministic control-safe rendering for dashboard snapshots."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum

from ansiblectl.application.dashboard import (
    DashboardConsumerRow,
    DashboardExecutionRow,
    DashboardSnapshot,
)

MIN_DASHBOARD_COLUMNS = 80
MIN_DASHBOARD_ROWS = 24


class DashboardPanel(IntEnum):
    """Fixed dashboard panel order used by keyboard navigation."""

    STATUS = 0
    EXECUTIONS = 1
    CONSUMERS = 2


@dataclass(frozen=True)
class DashboardViewState:
    """Presentation-only selection state for one frame."""

    panel: DashboardPanel = DashboardPanel.STATUS
    execution_index: int = 0
    consumer_index: int = 0
    refresh_failed: bool = False


def render_dashboard(
    snapshot: DashboardSnapshot,
    state: DashboardViewState,
    *,
    columns: int,
    rows: int,
) -> str:
    """Render one complete ASCII frame without executable terminal controls."""

    if columns < MIN_DASHBOARD_COLUMNS or rows < MIN_DASHBOARD_ROWS:
        return _small_terminal_frame(columns, rows)
    if not isinstance(state.panel, DashboardPanel):
        raise ValueError("Dashboard panel selection is invalid.")
    if state.execution_index < 0 or state.consumer_index < 0:
        raise ValueError("Dashboard row selection is invalid.")

    remaining = rows - 7
    execution_height = remaining // 2
    consumer_height = remaining - execution_height
    lines = [_fit_fixed("ansiblectl dashboard", columns)]
    lines.extend(_status_panel(snapshot, state, columns))
    lines.extend(_execution_panel(snapshot, state, columns, execution_height))
    lines.extend(_consumer_panel(snapshot, state, columns, consumer_height))
    footer = (
        "Refresh failed; showing previous snapshot. | r refresh | q quit"
        if state.refresh_failed
        else "Tab/arrow panel | j/k row | r refresh | q quit"
    )
    lines.append(_fit_fixed(footer, columns))
    assert len(lines) == rows
    return "\n".join(lines)


def terminal_safe_ascii(value: object, width: int) -> str:
    """Return one width-bounded printable ASCII scalar without arbitrary conversion."""

    if width < 0:
        raise ValueError("Dashboard cell width cannot be negative.")
    tokens = _scalar_tokens(value)
    length = sum(len(token) for token in tokens)
    if length <= width:
        return "".join(tokens)
    if width <= 3:
        return "." * width
    available = width - 3
    selected: list[str] = []
    used = 0
    for token in tokens:
        if used + len(token) > available:
            break
        selected.append(token)
        used += len(token)
    return "".join(selected) + "..."


def _scalar_tokens(value: object) -> tuple[str, ...]:
    if value is None:
        text = "-"
    elif isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, int):
        text = str(value)
    elif isinstance(value, float):
        text = f"{value:.3f}" if math.isfinite(value) else "-"
    elif isinstance(value, str):
        text = value
    else:
        text = "<unsupported>"
    return tuple(_character_token(character) for character in text)


def _character_token(character: str) -> str:
    code = ord(character)
    if character == "\\" or code < 32 or 127 <= code <= 159:
        return f"\\x{code:02x}"
    if 32 <= code <= 126:
        return character
    if code <= 0xFFFF:
        return f"\\u{code:04x}"
    return f"\\U{code:08x}"


def _small_terminal_frame(columns: int, rows: int) -> str:
    safe_columns = max(0, columns)
    safe_rows = max(0, rows)
    fixed = (
        "ansiblectl dashboard",
        "Terminal must be at least 80 columns by 24 rows.",
        "r refresh | q quit",
    )
    lines = [_fit_fixed(line, safe_columns) for line in fixed[:safe_rows]]
    lines.extend(" " * safe_columns for _ in range(safe_rows - len(lines)))
    return "\n".join(lines)


def _status_panel(
    snapshot: DashboardSnapshot, state: DashboardViewState, columns: int
) -> list[str]:
    counts = " ".join(
        f"{terminal_safe_ascii(item.name, 9)}:{terminal_safe_ascii(item.count, 4)}"
        for item in snapshot.execution_status_counts
    )
    content = (
        f"Version: {terminal_safe_ascii(snapshot.version, columns - 12)}",
        f"State: {terminal_safe_ascii(snapshot.message, columns - 10)}",
        f"Executions: {terminal_safe_ascii(snapshot.execution_total, 6)} {counts}",
    )
    return _panel("Status", state.panel is DashboardPanel.STATUS, content, columns, 5)


def _execution_panel(
    snapshot: DashboardSnapshot,
    state: DashboardViewState,
    columns: int,
    height: int,
) -> list[str]:
    content_height = height - 2
    header = _execution_line(None, False)
    visible_rows = max(0, content_height - 1)
    selected = min(state.execution_index, max(0, len(snapshot.executions) - 1))
    start = _window_start(selected, len(snapshot.executions), visible_rows)
    content = [header]
    content.extend(
        _execution_line(record, index == selected and state.panel is DashboardPanel.EXECUTIONS)
        for index, record in enumerate(
            snapshot.executions[start : start + visible_rows], start=start
        )
    )
    return _panel("Executions", state.panel is DashboardPanel.EXECUTIONS, content, columns, height)


def _execution_line(record: DashboardExecutionRow | None, selected: bool) -> str:
    values: tuple[object, ...]
    if record is None:
        values = ("TIME", "ID", "STATUS", "OPERATION", "MODE", "EXIT", "SECONDS")
    else:
        values = (
            record.timestamp,
            record.execution_id,
            record.status,
            record.operation,
            record.mode,
            record.exit_code,
            record.elapsed_seconds,
        )
    widths = (20, 12, 10, 10, 5, 4, 8)
    marker = ">" if selected else " "
    return (
        marker
        + " "
        + " ".join(
            terminal_safe_ascii(value, width).ljust(width)
            for value, width in zip(values, widths, strict=True)
        )
    )


def _consumer_panel(
    snapshot: DashboardSnapshot,
    state: DashboardViewState,
    columns: int,
    height: int,
) -> list[str]:
    content_height = height - 2
    header = _consumer_line(None, False)
    visible_rows = max(0, content_height - 1)
    selected = min(state.consumer_index, max(0, len(snapshot.consumers) - 1))
    start = _window_start(selected, len(snapshot.consumers), visible_rows)
    content = [header]
    content.extend(
        _consumer_line(consumer, index == selected and state.panel is DashboardPanel.CONSUMERS)
        for index, consumer in enumerate(
            snapshot.consumers[start : start + visible_rows], start=start
        )
    )
    return _panel("Consumers", state.panel is DashboardPanel.CONSUMERS, content, columns, height)


def _consumer_line(consumer: DashboardConsumerRow | None, selected: bool) -> str:
    values: tuple[object, ...]
    if consumer is None:
        values = ("ID", "STATE", "EVENTS", "PENDING", "SEQUENCE", "TRIES", "NEXT")
    else:
        values = (
            consumer.consumer_id,
            consumer.state,
            consumer.event_count,
            consumer.pending_count,
            consumer.lowest_pending_sequence,
            consumer.attempt_count,
            consumer.next_attempt_at,
        )
    widths = (15, 12, 6, 7, 8, 5, 12)
    marker = ">" if selected else " "
    return (
        marker
        + " "
        + " ".join(
            terminal_safe_ascii(value, width).ljust(width)
            for value, width in zip(values, widths, strict=True)
        )
    )


def _panel(
    title: str,
    selected: bool,
    content: tuple[str, ...] | list[str],
    columns: int,
    height: int,
) -> list[str]:
    inner = columns - 2
    label = f" {'*' if selected else '-'} {title} "
    top = "+" + _fit_fixed(label, inner, fill="-") + "+"
    body = ["|" + _fit_fixed(line, inner) + "|" for line in content[: height - 2]]
    body.extend("|" + " " * inner + "|" for _ in range(height - 2 - len(body)))
    return [top, *body, "+" + "-" * inner + "+"]


def _window_start(selected: int, total: int, visible: int) -> int:
    if visible <= 0 or total <= visible:
        return 0
    return min(max(0, selected - visible + 1), total - visible)


def _fit_fixed(value: str, width: int, *, fill: str = " ") -> str:
    if width <= 0:
        return ""
    return value[:width].ljust(width, fill)


__all__ = [
    "DashboardPanel",
    "DashboardViewState",
    "MIN_DASHBOARD_COLUMNS",
    "MIN_DASHBOARD_ROWS",
    "render_dashboard",
    "terminal_safe_ascii",
]

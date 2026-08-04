"""Deterministic terminal-safe dashboard rendering tests."""

from dataclasses import replace

import pytest

from ansiblectl.application.dashboard import (
    DashboardConsumerRow,
    DashboardCount,
    DashboardExecutionRow,
    DashboardSnapshot,
)
from ansiblectl.cli.dashboard_rendering import (
    DashboardPanel,
    DashboardViewState,
    render_dashboard,
    terminal_safe_ascii,
)


def _snapshot(marker: str = "safe") -> DashboardSnapshot:
    return DashboardSnapshot(
        version=f"0.17.0-{marker}",
        message=f"ready-{marker}",
        execution_total=1,
        execution_status_counts=(
            DashboardCount("completed", 1),
            DashboardCount("failed", 0),
            DashboardCount("timed_out", 0),
            DashboardCount("cancelled", 0),
        ),
        execution_mode_counts=(DashboardCount("check", 1), DashboardCount("apply", 0)),
        executions=(
            DashboardExecutionRow(
                f"time-{marker}",
                f"id-{marker}",
                f"status-{marker}",
                f"operation-{marker}",
                "check",
                0,
                1.25,
            ),
        ),
        consumers=(
            DashboardConsumerRow(
                f"consumer-{marker}", 4, 1, 4, 2, f"next-{marker}", f"state-{marker}"
            ),
        ),
    )


def test_large_frame_has_fixed_dimensions_and_three_panels() -> None:
    frame = render_dashboard(_snapshot(), DashboardViewState(), columns=100, rows=30)
    lines = frame.splitlines()

    assert len(lines) == 30
    assert all(len(line) == 100 for line in lines)
    assert sum("Status" in line for line in lines) == 1
    assert sum("- Executions" in line for line in lines) == 1
    assert sum("- Consumers" in line for line in lines) == 1
    assert "* Status" in frame
    assert "0.17.0-safe" in frame
    assert "consumer-safe" in frame
    assert "1.250" in frame


@pytest.mark.parametrize(("columns", "rows"), [(79, 24), (80, 23), (0, 0), (-1, -1)])
def test_small_terminal_frame_contains_no_dynamic_values(columns: int, rows: int) -> None:
    frame = render_dashboard(
        _snapshot("forbidden-dynamic"), DashboardViewState(), columns=columns, rows=rows
    )

    assert "forbidden-dynamic" not in frame
    assert len(frame.splitlines()) == max(0, rows)
    assert all(len(line) == max(0, columns) for line in frame.splitlines())


def test_every_character_class_is_escaped_and_never_executes_controls() -> None:
    value = "A\\\x00\x1b\x7f\x85\n\u2028\u202e\u200b\ud800\U0001f680Z"

    rendered = terminal_safe_ascii(value, 200)

    assert rendered == ("A\\x5c\\x00\\x1b\\x7f\\x85\\x0a\\u2028\\u202e\\u200b\\ud800\\U0001f680Z")
    assert all(character == " " or 33 <= ord(character) <= 126 for character in rendered)
    assert "\x1b" not in rendered
    assert "\n" not in rendered


def test_truncation_occurs_only_between_escape_tokens() -> None:
    assert terminal_safe_ascii("abéz", 10) == "ab\\u00e9z"
    assert terminal_safe_ascii("abéz", 9) == "ab\\u00e9z"
    assert terminal_safe_ascii("abéz", 8) == "ab..."
    assert terminal_safe_ascii("abcdef", 5) == "ab..."
    assert terminal_safe_ascii("abcdef", 3) == "..."
    assert terminal_safe_ascii("abcdef", 2) == ".."
    assert terminal_safe_ascii("abcdef", 0) == ""


def test_unsupported_values_never_invoke_string_or_repr() -> None:
    class Hostile:
        def __str__(self) -> str:
            raise AssertionError("str called")

        def __repr__(self) -> str:
            raise AssertionError("repr called")

    assert terminal_safe_ascii(Hostile(), 20) == "<unsupported>"
    assert terminal_safe_ascii(float("inf"), 20) == "-"
    assert terminal_safe_ascii(None, 20) == "-"
    with pytest.raises(ValueError, match="cannot be negative"):
        terminal_safe_ascii("value", -1)


def test_dynamic_injection_vectors_remain_printable_ascii_in_complete_frame() -> None:
    marker = "\\\x1b[2J\n\u202eé"
    frame = render_dashboard(
        _snapshot(marker),
        DashboardViewState(panel=DashboardPanel.CONSUMERS),
        columns=120,
        rows=30,
    )

    assert "\x1b" not in frame
    assert "\u202e" not in frame
    assert "é" not in frame
    assert all(character == "\n" or 32 <= ord(character) <= 126 for character in frame)
    assert "* Consumers" in frame


def test_selection_windows_rows_and_refresh_marker_without_query_data() -> None:
    snapshot = replace(
        _snapshot(),
        executions=tuple(
            replace(_snapshot().executions[0], execution_id=f"run-{index:03d}")
            for index in range(20)
        ),
    )
    frame = render_dashboard(
        snapshot,
        DashboardViewState(
            panel=DashboardPanel.EXECUTIONS,
            execution_index=19,
            refresh_failed=True,
        ),
        columns=100,
        rows=24,
    )

    assert "* Executions" in frame
    assert "> time-safe" in frame
    assert "run-019" in frame
    assert "run-000" not in frame
    assert "Refresh failed; showing previous snapshot." in frame


def test_invalid_selection_state_fails_before_rendering() -> None:
    with pytest.raises(ValueError, match="panel selection"):
        render_dashboard(
            _snapshot(),
            DashboardViewState(panel=3),  # type: ignore[arg-type]
            columns=80,
            rows=24,
        )
    with pytest.raises(ValueError, match="row selection"):
        render_dashboard(_snapshot(), DashboardViewState(execution_index=-1), columns=80, rows=24)

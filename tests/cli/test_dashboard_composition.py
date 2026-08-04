"""Dashboard composition boundary tests."""

from pathlib import Path

from ansiblectl import __version__
from ansiblectl.application.dashboard import MAX_DASHBOARD_EXECUTIONS
from ansiblectl.cli.composition import (
    build_dashboard_snapshot_service,
    build_workspace_service,
)


def test_dashboard_composes_one_workspace_read_only_queries(tmp_path: Path) -> None:
    build_workspace_service().initialize(tmp_path)

    service = build_dashboard_snapshot_service(tmp_path)
    snapshot = service.snapshot()

    assert snapshot.version == __version__
    assert snapshot.execution_total == 0
    assert snapshot.executions == ()
    assert snapshot.consumers == ()
    assert set(service.queries.__dict__) == {
        "status",
        "execution_summary",
        "executions",
        "consumers",
    }
    assert MAX_DASHBOARD_EXECUTIONS == 100

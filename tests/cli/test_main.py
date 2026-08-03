"""CLI contract tests."""

import json
from io import StringIO
from pathlib import Path

import pytest

from ansiblectl.application.status import Status
from ansiblectl.cli.main import EXIT_EXPECTED_FAILURE, EXIT_INVALID_INPUT, EXIT_SUCCESS, main
from ansiblectl.domain.errors import WorkspaceNotFoundError
from ansiblectl.domain.inventory import Host, ResolvedInventory
from ansiblectl.domain.workspace import Workspace


class FakeStatusService:
    def get_status(self) -> Status:
        return Status(version="9.9.9", message="Fake service is ready.")


def test_status_uses_injected_application_service() -> None:
    output = StringIO()

    result = main(
        ["--output-format", "json", "status"], status_service=FakeStatusService(), stdout=output
    )

    assert result == EXIT_SUCCESS
    assert output.getvalue() == '{"message": "Fake service is ready.", "version": "9.9.9"}\n'


def test_help_lists_global_options_and_status_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--help"])

    captured = capsys.readouterr()
    assert raised.value.code == EXIT_SUCCESS
    assert "--workspace" in captured.out
    assert "--output-format" in captured.out
    assert "status" in captured.out


def test_invalid_argument_uses_documented_invalid_input_exit_code(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--unknown"])

    captured = capsys.readouterr()
    assert raised.value.code == EXIT_INVALID_INPUT
    assert "error:" in captured.err


class FakeWorkspaceService:
    def initialize(self, path: Path) -> Workspace:
        return Workspace(
            root=path.resolve(),
            metadata_path=path.resolve() / ".ansiblectl/workspace.json",
            schema_version=1,
        )

    def resolve(self, explicit_path: Path | None, current_directory: Path) -> Workspace:
        if explicit_path is None:
            raise WorkspaceNotFoundError("Run 'ansiblectl workspace init'.")
        return self.initialize(explicit_path)


def test_workspace_init_renders_the_injected_service_result(tmp_path: Path) -> None:
    output = StringIO()

    result = main(
        ["--output-format", "json", "workspace", "init", str(tmp_path)],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_SUCCESS
    assert f'"root": "{tmp_path}"' in output.getvalue()


def test_workspace_show_outside_a_workspace_is_actionable(tmp_path: Path) -> None:
    error = StringIO()

    result = main(
        ["workspace", "show"],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        stderr=error,
        current_directory=tmp_path,
    )

    assert result == EXIT_EXPECTED_FAILURE
    assert "workspace init" in error.getvalue()


def test_workspace_init_uses_the_composition_root(tmp_path: Path) -> None:
    output = StringIO()

    result = main(["--output-format", "json", "workspace", "init", str(tmp_path)], stdout=output)

    assert result == EXIT_SUCCESS
    assert '"schema_version": 1' in output.getvalue()
    assert (tmp_path / ".ansiblectl/workspace.json").is_file()


class FakeInventoryService:
    def resolve(self) -> ResolvedInventory:
        host = Host("web-1", "192.0.2.10", {"role": "web"}, "fixture")
        return ResolvedInventory({"web-1": host}, {"web": ("web-1",)}, {"web-1": "fixture"}, ())


def test_inventory_show_renders_injected_resolved_inventory() -> None:
    output = StringIO()

    result = main(
        ["--output-format", "json", "inventory", "show"],
        inventory_service=FakeInventoryService(),  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_SUCCESS
    assert json.loads(output.getvalue()) == {
        "diagnostics": [],
        "groups": {"web": ["web-1"]},
        "hosts": {"web-1": {"address": "192.0.2.10", "variables": {"role": "web"}}},
        "provenance": {"web-1": "fixture"},
    }


def test_inventory_show_uses_workspace_yaml_provider(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    assert main(["workspace", "init", str(workspace)], stdout=StringIO()) == EXIT_SUCCESS
    inventory = workspace / "inventory/hosts.yml"
    inventory.parent.mkdir()
    inventory.write_text(
        "all:\n  children:\n    web:\n      hosts:\n        web-1:\n"
        "          ansible_host: 192.0.2.10\n",
        encoding="utf-8",
    )
    output = StringIO()

    result = main(
        ["--workspace", str(workspace), "--output-format", "json", "inventory", "show"],
        stdout=output,
    )

    assert result == EXIT_SUCCESS
    assert json.loads(output.getvalue())["hosts"]["web-1"]["address"] == "192.0.2.10"


def test_inventory_source_cannot_escape_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    assert main(["workspace", "init", str(workspace)], stdout=StringIO()) == EXIT_SUCCESS
    error = StringIO()

    result = main(
        ["--workspace", str(workspace), "inventory", "show", "--source", "../outside.yml"],
        stderr=error,
    )

    assert result == EXIT_EXPECTED_FAILURE
    assert "inside the selected workspace" in error.getvalue()

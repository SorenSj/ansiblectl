"""CLI contract tests."""

import json
from io import StringIO
from pathlib import Path

import pytest

from ansiblectl.application.execution import GovernedExecutionResult
from ansiblectl.application.status import Status
from ansiblectl.cli.main import EXIT_EXPECTED_FAILURE, EXIT_INVALID_INPUT, EXIT_SUCCESS, main
from ansiblectl.domain.errors import ExecutionError, WorkspaceNotFoundError
from ansiblectl.domain.execution import (
    ExecutionMode,
    ExecutionRecord,
    ExecutionResult,
    ExecutionRetentionResult,
    ExecutionStatus,
    ExecutionTargeting,
)
from ansiblectl.domain.inventory import Host, ResolvedInventory
from ansiblectl.domain.plugins import ProviderDescriptor
from ansiblectl.domain.policy import EnforcementMode, PolicyFinding, PolicyReport
from ansiblectl.domain.repository import RepositoryRequest, RepositoryResult
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
    assert "repository" in captured.out
    assert "execution" in captured.out


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


class FakeRepositoryService:
    def __init__(self, dirty: bool = False) -> None:
        self.dirty = dirty
        self.calls: list[tuple[str, RepositoryRequest]] = []

    def inspect(self, request: RepositoryRequest) -> RepositoryResult:
        self.calls.append(("inspect", request))
        return RepositoryResult(request.repository_path, request.revision, self.dirty)

    def sync(self, request: RepositoryRequest) -> RepositoryResult:
        self.calls.append(("sync", request))
        return RepositoryResult(request.repository_path, request.revision, False)


def test_repository_inspect_builds_workspace_scoped_request(tmp_path: Path) -> None:
    service, output = FakeRepositoryService(dirty=True), StringIO()

    result = main(
        [
            "--workspace",
            str(tmp_path),
            "--output-format",
            "json",
            "repository",
            "inspect",
            "repo",
            "--revision",
            "main",
        ],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        repository_service=service,  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_SUCCESS
    assert service.calls[0][1] == RepositoryRequest(
        tmp_path.resolve(), (tmp_path / "repo").resolve(), "main"
    )
    assert json.loads(output.getvalue())["dirty"] is True


def test_repository_sync_reports_target_before_service_call(tmp_path: Path) -> None:
    service, output, error = FakeRepositoryService(), StringIO(), StringIO()

    result = main(
        [
            "--workspace",
            str(tmp_path),
            "repository",
            "sync",
            "repo",
            "--revision",
            "release-1",
        ],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        repository_service=service,  # type: ignore[arg-type]
        stdout=output,
        stderr=error,
    )

    assert result == EXIT_SUCCESS
    assert service.calls[0][0] == "sync"
    assert "repo" in error.getvalue()
    assert "release-1" in error.getvalue()


def test_repository_path_cannot_escape_workspace(tmp_path: Path) -> None:
    service, error = FakeRepositoryService(), StringIO()

    result = main(
        [
            "--workspace",
            str(tmp_path),
            "repository",
            "inspect",
            "../outside",
            "--revision",
            "main",
        ],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        repository_service=service,  # type: ignore[arg-type]
        stderr=error,
    )

    assert result == EXIT_EXPECTED_FAILURE
    assert service.calls == []
    assert "inside the selected workspace" in error.getvalue()


class FakePluginDiscoveryService:
    def __init__(self) -> None:
        self.locations: list[Path] = []

    def discover_files(self, locations: list[Path]) -> dict[str, ProviderDescriptor]:
        self.locations = locations
        return {
            "demo": ProviderDescriptor(
                "demo", "1.0", "0.1", ("provider",), "schema.json", ("network",), str(locations[0])
            )
        }


def test_plugin_validate_renders_descriptor_without_loading_code(tmp_path: Path) -> None:
    service, output = FakePluginDiscoveryService(), StringIO()

    result = main(
        [
            "--workspace",
            str(tmp_path),
            "--output-format",
            "json",
            "plugin",
            "validate",
            "plugins/demo.yaml",
        ],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        plugin_service=service,  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_SUCCESS
    assert service.locations == [(tmp_path / "plugins/demo.yaml").resolve()]
    assert json.loads(output.getvalue())["plugins"][0]["identity"] == "demo"


def test_plugin_manifest_path_cannot_escape_workspace(tmp_path: Path) -> None:
    service, error = FakePluginDiscoveryService(), StringIO()

    result = main(
        ["--workspace", str(tmp_path), "plugin", "validate", "../outside.yaml"],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        plugin_service=service,  # type: ignore[arg-type]
        stderr=error,
    )

    assert result == EXIT_EXPECTED_FAILURE
    assert service.locations == []
    assert "inside the selected workspace" in error.getvalue()


class FakeRunService:
    def run_check(
        self,
        workspace_root: Path,
        playbook_identifier: Path,
        revision: str,
        environment: object,
        timeout_seconds: float,
        policy_mode: EnforcementMode,
        targeting: ExecutionTargeting,
    ) -> GovernedExecutionResult:
        assert workspace_root.is_absolute()
        assert playbook_identifier == Path("playbooks/site.yml")
        assert revision == "main"
        assert timeout_seconds == 30
        assert policy_mode is EnforcementMode.DENY
        assert targeting == ExecutionTargeting("web:&staging", ("deploy", "config"), ("slow",))
        return GovernedExecutionResult(
            PolicyReport((), policy_mode),
            ExecutionResult("run-1", ExecutionStatus.COMPLETED, 0, 0.1, targeting=targeting),
        )

    def run_apply(
        self,
        workspace_root: Path,
        playbook_identifier: Path,
        revision: str,
        environment: object,
        timeout_seconds: float,
        policy_mode: EnforcementMode,
        confirmed: bool,
        targeting: ExecutionTargeting,
    ) -> GovernedExecutionResult:
        assert confirmed is True
        return GovernedExecutionResult(
            PolicyReport((), policy_mode),
            ExecutionResult(
                "run-apply",
                ExecutionStatus.COMPLETED,
                0,
                0.1,
                targeting=targeting,
                mode=ExecutionMode.APPLY,
            ),
        )


def test_run_check_renders_injected_execution_result(tmp_path: Path) -> None:
    output = StringIO()

    result = main(
        [
            "--workspace",
            str(tmp_path),
            "--output-format",
            "json",
            "run",
            "--playbook",
            "playbooks/site.yml",
            "--revision",
            "main",
            "--check",
            "--timeout",
            "30",
            "--limit",
            "web:&staging",
            "--tags",
            "deploy,config",
            "--skip-tags",
            "slow",
        ],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        run_service=FakeRunService(),  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_SUCCESS
    assert json.loads(output.getvalue())["execution"]["status"] == "completed"
    assert json.loads(output.getvalue())["execution"]["targeting"]["limit"] == "web:&staging"
    assert json.loads(output.getvalue())["policy"]["allowed"] is True


class FailedRunService(FakeRunService):
    def run_check(
        self,
        workspace_root: Path,
        playbook_identifier: Path,
        revision: str,
        environment: object,
        timeout_seconds: float,
        policy_mode: EnforcementMode,
        targeting: ExecutionTargeting,
    ) -> GovernedExecutionResult:
        return GovernedExecutionResult(
            PolicyReport((), policy_mode),
            ExecutionResult(
                "run-2",
                ExecutionStatus.TIMED_OUT,
                None,
                30.0,
                "/private/run/stdout.log",
                "/private/run/stderr.log",
                "Timeout reached.",
            ),
        )


def test_run_failure_uses_expected_failure_exit_and_safe_diagnostic(tmp_path: Path) -> None:
    output = StringIO()

    result = main(
        [
            "--workspace",
            str(tmp_path),
            "run",
            "--playbook",
            "playbooks/site.yml",
            "--revision",
            "main",
            "--check",
        ],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        run_service=FailedRunService(),  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_EXPECTED_FAILURE
    assert "timed_out" in output.getvalue()
    assert "Timeout reached" in output.getvalue()
    assert "Stdout: /private/run/stdout.log" in output.getvalue()
    assert "Stderr: /private/run/stderr.log" in output.getvalue()


def test_run_rejects_empty_targeting_before_service_invocation(tmp_path: Path) -> None:
    error = StringIO()

    result = main(
        [
            "--workspace",
            str(tmp_path),
            "run",
            "--playbook",
            "playbooks/site.yml",
            "--revision",
            "main",
            "--check",
            "--tags",
            "deploy,,config",
        ],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        run_service=FakeRunService(),  # type: ignore[arg-type]
        stderr=error,
    )

    assert result == EXIT_EXPECTED_FAILURE
    assert "targeting values" in error.getvalue()


def test_run_apply_requires_confirmation_and_records_mode(tmp_path: Path) -> None:
    error = StringIO()
    arguments = [
        "--workspace",
        str(tmp_path),
        "--output-format",
        "json",
        "run",
        "--playbook",
        "playbooks/site.yml",
        "--revision",
        "main",
        "--apply",
    ]

    assert (
        main(
            arguments,
            workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
            run_service=FakeRunService(),  # type: ignore[arg-type]
            stderr=error,
        )
        == EXIT_INVALID_INPUT
    )
    output = StringIO()
    result = main(
        [*arguments, "--confirm"],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        run_service=FakeRunService(),  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_SUCCESS
    assert json.loads(output.getvalue())["execution"]["mode"] == "apply"


class DeniedRunService(FakeRunService):
    def run_check(
        self,
        workspace_root: Path,
        playbook_identifier: Path,
        revision: str,
        environment: object,
        timeout_seconds: float,
        policy_mode: EnforcementMode,
        targeting: ExecutionTargeting,
    ) -> GovernedExecutionResult:
        finding = PolicyFinding("RUN-001", "high", "Execution denied", str(playbook_identifier))
        return GovernedExecutionResult(PolicyReport((finding,), policy_mode), None)


def test_run_deny_renders_policy_without_execution(tmp_path: Path) -> None:
    output = StringIO()

    result = main(
        [
            "--workspace",
            str(tmp_path),
            "--output-format",
            "json",
            "run",
            "--playbook",
            "playbooks/site.yml",
            "--revision",
            "main",
            "--check",
            "--policy-mode",
            "deny",
        ],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        run_service=DeniedRunService(),  # type: ignore[arg-type]
        stdout=output,
    )

    payload = json.loads(output.getvalue())
    assert result == EXIT_EXPECTED_FAILURE
    assert payload["execution"] is None
    assert payload["policy"]["findings"][0]["rule_id"] == "RUN-001"


class FakeExecutionHistoryService:
    record = ExecutionRecord(
        "2026-08-03T12:00:00+00:00",
        "run-1",
        ExecutionStatus.COMPLETED,
        0,
        1.25,
        "/workspace/.ansiblectl/runs/stdout.log",
        targeting=ExecutionTargeting("web", ("deploy",), ("slow",)),
        requested_revision="main",
        resolved_revision="abc123",
        inventory_digest="sha256:inventory",
    )

    def list(self) -> tuple[ExecutionRecord, ...]:
        return (self.record,)

    def get(self, execution_id: str) -> ExecutionRecord:
        if execution_id != self.record.execution_id:
            raise ExecutionError(f"Execution '{execution_id}' was not found in this workspace.")
        return self.record

    def retention(self, keep: int, *, apply: bool) -> ExecutionRetentionResult:
        assert keep == 0
        return ExecutionRetentionResult(0, (self.record.execution_id,), apply)


def test_execution_list_renders_safe_machine_history(tmp_path: Path) -> None:
    output = StringIO()

    result = main(
        ["--workspace", str(tmp_path), "--output-format", "json", "execution", "list"],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        execution_history_service=FakeExecutionHistoryService(),  # type: ignore[arg-type]
        stdout=output,
    )

    payload = json.loads(output.getvalue())
    assert result == EXIT_SUCCESS
    assert payload["executions"][0]["execution_id"] == "run-1"
    assert payload["executions"][0]["stdout_reference"].endswith("stdout.log")
    assert payload["executions"][0]["targeting"] == {
        "limit": "web",
        "skip_tags": ["slow"],
        "tags": ["deploy"],
    }
    assert payload["executions"][0]["requested_revision"] == "main"
    assert payload["executions"][0]["resolved_revision"] == "abc123"
    assert payload["executions"][0]["inventory_digest"] == "sha256:inventory"


def test_execution_show_renders_one_human_record(tmp_path: Path) -> None:
    output = StringIO()

    result = main(
        ["--workspace", str(tmp_path), "execution", "show", "run-1"],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        execution_history_service=FakeExecutionHistoryService(),  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_SUCCESS
    assert "Execution: run-1" in output.getvalue()
    assert "Status: completed" in output.getvalue()


def test_execution_show_reports_unknown_identifier(tmp_path: Path) -> None:
    error = StringIO()

    result = main(
        ["--workspace", str(tmp_path), "execution", "show", "missing"],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        execution_history_service=FakeExecutionHistoryService(),  # type: ignore[arg-type]
        stderr=error,
    )

    assert result == EXIT_EXPECTED_FAILURE
    assert "was not found" in error.getvalue()


def test_execution_prune_previews_unless_apply_is_explicit(tmp_path: Path) -> None:
    output = StringIO()

    result = main(
        [
            "--workspace",
            str(tmp_path),
            "--output-format",
            "json",
            "execution",
            "prune",
            "--keep",
            "0",
        ],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        execution_history_service=FakeExecutionHistoryService(),  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_SUCCESS
    assert json.loads(output.getvalue()) == {
        "applied": False,
        "removed_execution_ids": ["run-1"],
        "retained_count": 0,
        "schema_version": 1,
    }


def test_execution_prune_applies_only_with_explicit_flag(tmp_path: Path) -> None:
    output = StringIO()

    result = main(
        ["--workspace", str(tmp_path), "execution", "prune", "--keep", "0", "--apply"],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        execution_history_service=FakeExecutionHistoryService(),  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_SUCCESS
    assert "Applied: retain 0 execution(s)" in output.getvalue()
    assert "Execution: run-1" in output.getvalue()

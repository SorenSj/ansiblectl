"""CLI contract tests."""

import json
from io import StringIO
from pathlib import Path

import pytest

from ansiblectl.application.execution import GovernedExecutionResult
from ansiblectl.application.execution_history import ExecutionSummary
from ansiblectl.application.inventory import InventoryValidationResult
from ansiblectl.application.playbook import PlaybookValidationResult, SyntaxCheckEvidence
from ansiblectl.application.run import RunPreflightResult
from ansiblectl.application.state import CacheEntrySummary
from ansiblectl.application.status import Status
from ansiblectl.cli.main import (
    EXIT_CANCELLED,
    EXIT_EXPECTED_FAILURE,
    EXIT_INVALID_INPUT,
    EXIT_SUCCESS,
    main,
)
from ansiblectl.domain.configuration import EffectiveConfiguration
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
from ansiblectl.domain.state import CacheEntry, StateInvalidationResult
from ansiblectl.domain.workspace import Workspace
from ansiblectl.infrastructure.workspace_state import WorkspaceStateStore


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
    assert "config" in captured.out
    assert "state" in captured.out
    assert "repository" in captured.out
    assert "playbook" in captured.out
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


class FakeConfigurationService:
    def resolve(self) -> EffectiveConfiguration:
        return EffectiveConfiguration(
            "demo",
            "warning",
            {"token": "vault:production-token"},
            {"project_name": "project", "log_level": "environment", "secrets": "project"},
        )


class FakeStateService:
    def inspect(self) -> tuple[CacheEntrySummary, ...]:
        return (CacheEntrySummary("inventory", "git:main", "revision changes"),)

    def invalidate(self, name: str, *, apply: bool = False) -> StateInvalidationResult:
        return StateInvalidationResult(name, True, apply, 0)


def test_state_show_renders_only_safe_cache_metadata(tmp_path: Path) -> None:
    output = StringIO()

    result = main(
        ["--workspace", str(tmp_path), "--output-format", "json", "state", "show"],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        state_service=FakeStateService(),  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_SUCCESS
    assert json.loads(output.getvalue()) == {
        "entries": [
            {
                "invalidation_condition": "revision changes",
                "name": "inventory",
                "source_identity": "git:main",
            }
        ],
        "schema_version": 1,
    }


def test_state_show_omits_cached_values_from_local_store(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    assert main(["workspace", "init", str(workspace)], stdout=StringIO()) == EXIT_SUCCESS
    WorkspaceStateStore(workspace).write(
        {"inventory": CacheEntry("git:main", "revision changes", {"token": "secret-value"})}
    )
    output = StringIO()

    result = main(
        ["--workspace", str(workspace), "--output-format", "json", "state", "show"],
        stdout=output,
    )

    assert result == EXIT_SUCCESS
    assert "secret-value" not in output.getvalue()
    assert json.loads(output.getvalue())["entries"][0]["name"] == "inventory"


def test_state_invalidate_is_preview_only_without_apply(tmp_path: Path) -> None:
    output = StringIO()

    result = main(
        [
            "--workspace",
            str(tmp_path),
            "--output-format",
            "json",
            "state",
            "invalidate",
            "inventory",
        ],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        state_service=FakeStateService(),  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_SUCCESS
    assert json.loads(output.getvalue()) == {
        "applied": False,
        "existed": True,
        "name": "inventory",
        "remaining_count": 0,
        "schema_version": 1,
    }


def test_config_show_renders_redacted_effective_configuration(tmp_path: Path) -> None:
    output = StringIO()

    result = main(
        ["--workspace", str(tmp_path), "--output-format", "json", "config", "show"],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        configuration_service=FakeConfigurationService(),  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_SUCCESS
    assert json.loads(output.getvalue()) == {
        "log_level": "warning",
        "project_name": "demo",
        "provenance": {
            "log_level": "environment",
            "project_name": "project",
            "secrets": "project",
        },
        "schema_version": 1,
        "secrets": {"token": "<redacted>"},
    }
    assert "production-token" not in output.getvalue()


def test_config_show_reports_invalid_source_safely(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    assert main(["workspace", "init", str(workspace)], stdout=StringIO()) == EXIT_SUCCESS
    (workspace / "ansiblectl.yaml").write_text(
        "schema_version: 1\nunknown: value\n", encoding="utf-8"
    )
    error = StringIO()

    result = main(["--workspace", str(workspace), "config", "show"], stderr=error)

    assert result == EXIT_EXPECTED_FAILURE
    assert "Unknown field 'unknown'" in error.getvalue()
    assert "Correct the identified configuration source" in error.getvalue()


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


class FakeInventoryValidationService:
    def validate(
        self, workspace_root: Path, environment: object, timeout_seconds: float
    ) -> InventoryValidationResult:
        assert workspace_root.is_absolute()
        assert timeout_seconds == 12.0
        return InventoryValidationResult(
            "sha256:inventory",
            ExecutionResult(
                "inventory-1",
                ExecutionStatus.COMPLETED,
                0,
                0.25,
                "runs/inventory/stdout.log",
                inventory_digest="sha256:inventory",
                operation="inventory.validate",
            ),
        )


class FailingInventoryValidationService:
    def validate(
        self, workspace_root: Path, environment: object, timeout_seconds: float
    ) -> InventoryValidationResult:
        return InventoryValidationResult(
            "sha256:inventory",
            ExecutionResult(
                "inventory-2",
                ExecutionStatus.FAILED,
                1,
                0.5,
                stderr_reference="runs/inventory/stderr.log",
                diagnostic="Validator exited with status 1.",
                inventory_digest="sha256:inventory",
                operation="inventory.validate",
            ),
        )


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
        "digest": "sha256:e0d4471a9995a11e29a087dae9a3cd24941a874c36de085b6b83e9781e31f353",
        "groups": {"web": ["web-1"]},
        "hosts": {"web-1": {"address": "192.0.2.10", "variables": {"role": "web"}}},
        "provenance": {"web-1": "fixture"},
        "schema_version": 1,
    }


def test_inventory_show_human_output_includes_canonical_digest() -> None:
    output = StringIO()

    result = main(
        ["inventory", "show"],
        inventory_service=FakeInventoryService(),  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_SUCCESS
    assert "Digest: sha256:" in output.getvalue()


def test_inventory_validate_renders_safe_ansible_evidence(tmp_path: Path) -> None:
    output = StringIO()

    result = main(
        [
            "--workspace",
            str(tmp_path),
            "--output-format",
            "json",
            "inventory",
            "validate",
            "--timeout",
            "12",
        ],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        inventory_validation_service=FakeInventoryValidationService(),  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_SUCCESS
    assert json.loads(output.getvalue()) == {
        "diagnostic": None,
        "digest": "sha256:inventory",
        "elapsed_seconds": 0.25,
        "execution_id": "inventory-1",
        "exit_code": 0,
        "schema_version": 1,
        "status": "completed",
        "stderr_reference": None,
        "stdout_reference": "runs/inventory/stdout.log",
        "validator": "ansible-inventory --list",
    }


def test_inventory_validate_human_failure_returns_expected_exit(tmp_path: Path) -> None:
    output = StringIO()

    result = main(
        ["--workspace", str(tmp_path), "inventory", "validate"],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        inventory_validation_service=FailingInventoryValidationService(),  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_EXPECTED_FAILURE
    assert "Validator: ansible-inventory --list" in output.getvalue()
    assert "Status: failed" in output.getvalue()
    assert "Stderr: runs/inventory/stderr.log" in output.getvalue()
    assert "Diagnostic: Validator exited with status 1." in output.getvalue()


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
        return RepositoryResult(
            request.repository_path, request.revision, False, "abc123", "abc123"
        )


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


def test_repository_sync_json_has_no_progress_decoration(tmp_path: Path) -> None:
    service, output, error = FakeRepositoryService(), StringIO(), StringIO()

    result = main(
        [
            "--workspace",
            str(tmp_path),
            "--output-format",
            "json",
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
    assert error.getvalue() == ""
    payload = json.loads(output.getvalue())
    assert payload["revision"] == "release-1"
    assert payload["resolved_revision"] == "abc123"
    assert payload["head_revision"] == "abc123"


@pytest.mark.parametrize(
    ("command", "operation"),
    [
        (["workspace", "show"], "workspace show"),
        (["config", "show"], "config show"),
        (["state", "show"], "state show"),
        (["state", "invalidate", "inventory"], "state invalidate"),
        (["inventory", "show"], "inventory show"),
        (["repository", "inspect", "repo", "--revision", "main"], "repository inspect"),
        (["plugin", "validate", "plugin.yaml"], "plugin validate"),
        (["execution", "list"], "execution list"),
    ],
)
def test_workspace_scoped_failures_are_structured_in_json_mode(
    tmp_path: Path, command: list[str], operation: str
) -> None:
    output, error = StringIO(), StringIO()

    result = main(
        ["--output-format", "json", *command],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        stdout=output,
        stderr=error,
        current_directory=tmp_path,
    )

    assert result == EXIT_EXPECTED_FAILURE
    assert error.getvalue() == ""
    payload = json.loads(output.getvalue())
    assert payload["kind"] == "operational_failure"
    assert payload["operation"] == operation
    assert payload["remediation"] == "Initialize or select a valid workspace and retry."


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

    def discover_directory(self, location: Path) -> dict[str, ProviderDescriptor]:
        self.locations = [location]
        return {
            "demo": ProviderDescriptor(
                "demo", "1.0", "0.1", ("provider",), "schema.json", (), str(location)
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


def test_plugin_discover_uses_default_workspace_directory(tmp_path: Path) -> None:
    service, output = FakePluginDiscoveryService(), StringIO()

    result = main(
        ["--workspace", str(tmp_path), "--output-format", "json", "plugin", "discover"],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        plugin_service=service,  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_SUCCESS
    assert service.locations == [(tmp_path / "plugins").resolve()]
    assert json.loads(output.getvalue())["plugins"][0]["identity"] == "demo"


def test_plugin_discover_rejects_directory_symlink(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-plugins"
    outside.mkdir()
    (tmp_path / "plugins").symlink_to(outside, target_is_directory=True)
    service, error = FakePluginDiscoveryService(), StringIO()

    result = main(
        ["--workspace", str(tmp_path), "plugin", "discover"],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        plugin_service=service,  # type: ignore[arg-type]
        stderr=error,
    )

    assert result == EXIT_EXPECTED_FAILURE
    assert service.locations == []
    assert "must not be a symbolic link" in error.getvalue()


def test_plugin_permissions_previews_default_deny_without_loading_code(tmp_path: Path) -> None:
    service, output = FakePluginDiscoveryService(), StringIO()

    result = main(
        [
            "--workspace",
            str(tmp_path),
            "--output-format",
            "json",
            "plugin",
            "permissions",
            "plugins/demo.yaml",
        ],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        plugin_service=service,  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_SUCCESS
    assert service.locations == [(tmp_path / "plugins/demo.yaml").resolve()]
    assert json.loads(output.getvalue()) == {
        "denied": ["network"],
        "granted": [],
        "identity": "demo",
        "requested": ["network"],
        "schema_version": 1,
    }


def test_plugin_permissions_accepts_only_explicit_grant(tmp_path: Path) -> None:
    service, output = FakePluginDiscoveryService(), StringIO()

    result = main(
        [
            "--workspace",
            str(tmp_path),
            "--output-format",
            "json",
            "plugin",
            "permissions",
            "plugins/demo.yaml",
            "--grant",
            "network",
        ],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        plugin_service=service,  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_SUCCESS
    assert json.loads(output.getvalue())["granted"] == ["network"]
    assert json.loads(output.getvalue())["denied"] == []


def test_playbook_validate_reports_safe_selection_evidence(tmp_path: Path) -> None:
    playbook = tmp_path / "playbooks/site.yml"
    playbook.parent.mkdir()
    playbook.write_text("---\n- hosts: all\n", encoding="utf-8")
    output, error = StringIO(), StringIO()

    result = main(
        [
            "--workspace",
            str(tmp_path),
            "--output-format",
            "json",
            "playbook",
            "validate",
            "playbooks/site.yml",
            "--revision",
            "main",
        ],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        stdout=output,
        stderr=error,
    )

    assert result == EXIT_SUCCESS
    assert error.getvalue() == ""
    payload = json.loads(output.getvalue())
    assert payload["playbook_path"] == "playbooks/site.yml"
    assert payload["revision"] == "main"
    assert payload["digest"].startswith("sha256:")
    assert payload["validator"] == "ansiblectl.selection"
    assert str(tmp_path) not in output.getvalue()


def test_playbook_validate_rejects_workspace_escape_as_structured_failure(tmp_path: Path) -> None:
    output, error = StringIO(), StringIO()

    result = main(
        [
            "--workspace",
            str(tmp_path),
            "--output-format",
            "json",
            "playbook",
            "validate",
            "../outside.yml",
            "--revision",
            "main",
        ],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        stdout=output,
        stderr=error,
    )

    assert result == EXIT_EXPECTED_FAILURE
    assert error.getvalue() == ""
    payload = json.loads(output.getvalue())
    assert payload["kind"] == "operational_failure"
    assert payload["operation"] == "playbook validate"


class FakeSyntaxValidationService:
    def validate(
        self,
        workspace_root: Path,
        identifier: Path,
        revision: str,
        *,
        syntax_check: bool,
        environment: object,
        timeout_seconds: float,
    ) -> PlaybookValidationResult:
        assert syntax_check is True
        assert timeout_seconds == 15
        return PlaybookValidationResult(
            "playbooks/site.yml",
            revision,
            "sha256:playbook",
            (),
            "ansiblectl.selection",
            "0.1.0",
            SyntaxCheckEvidence(
                ExecutionStatus.FAILED,
                4,
                "ansible-playbook --syntax-check",
                "/private/stdout.log",
                "/private/stderr.log",
                None,
            ),
        )


def test_playbook_syntax_check_returns_classified_failure_and_provenance(tmp_path: Path) -> None:
    output, error = StringIO(), StringIO()

    result = main(
        [
            "--workspace",
            str(tmp_path),
            "--output-format",
            "json",
            "playbook",
            "validate",
            "playbooks/site.yml",
            "--revision",
            "main",
            "--syntax-check",
            "--timeout",
            "15",
        ],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        playbook_service=FakeSyntaxValidationService(),  # type: ignore[arg-type]
        stdout=output,
        stderr=error,
    )

    assert result == EXIT_EXPECTED_FAILURE
    assert error.getvalue() == ""
    syntax = json.loads(output.getvalue())["syntax_check"]
    assert syntax["status"] == "failed"
    assert syntax["exit_code"] == 4
    assert syntax["validator"] == "ansible-playbook --syntax-check"
    assert syntax["stderr_reference"] == "/private/stderr.log"


class FakeRunService:
    def preflight(
        self,
        workspace_root: Path,
        playbook_identifier: Path,
        revision: str,
        policy_mode: EnforcementMode,
        mode: ExecutionMode,
        targeting: ExecutionTargeting,
        verbosity: int,
        diff: bool,
    ) -> RunPreflightResult:
        return RunPreflightResult(
            PolicyReport((), policy_mode),
            mode,
            "playbooks/site.yml",
            revision,
            "abc123",
            "sha256:inventory",
            "sha256:playbook",
            targeting,
            verbosity,
            diff,
        )

    def run_check(
        self,
        workspace_root: Path,
        playbook_identifier: Path,
        revision: str,
        environment: object,
        timeout_seconds: float,
        policy_mode: EnforcementMode,
        targeting: ExecutionTargeting,
        verbosity: int,
        diff: bool,
    ) -> GovernedExecutionResult:
        assert workspace_root.is_absolute()
        assert playbook_identifier == Path("playbooks/site.yml")
        assert revision == "main"
        assert timeout_seconds == 30
        assert policy_mode is EnforcementMode.DENY
        assert verbosity == 2
        assert diff is True
        assert targeting == ExecutionTargeting("web:&staging", ("deploy", "config"), ("slow",))
        return GovernedExecutionResult(
            PolicyReport((), policy_mode),
            ExecutionResult(
                "run-1",
                ExecutionStatus.COMPLETED,
                0,
                0.1,
                targeting=targeting,
                verbosity=verbosity,
                diff=diff,
            ),
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
        verbosity: int,
        diff: bool,
    ) -> GovernedExecutionResult:
        assert confirmed is True
        assert verbosity == 0
        assert diff is False
        return GovernedExecutionResult(
            PolicyReport((), policy_mode),
            ExecutionResult(
                "run-apply",
                ExecutionStatus.COMPLETED,
                0,
                0.1,
                targeting=targeting,
                mode=ExecutionMode.APPLY,
                verbosity=verbosity,
                diff=diff,
            ),
        )


def test_run_preflight_renders_safe_evidence_without_execution(tmp_path: Path) -> None:
    output = StringIO()

    result = main(
        [
            "--workspace",
            str(tmp_path),
            "--output-format",
            "json",
            "-v",
            "run",
            "--playbook",
            "playbooks/site.yml",
            "--revision",
            "main",
            "--check",
            "--preflight",
            "--limit",
            "web",
        ],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        run_service=FakeRunService(),  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_SUCCESS
    assert json.loads(output.getvalue()) == {
        "diff": False,
        "inventory_digest": "sha256:inventory",
        "mode": "check",
        "playbook_digest": "sha256:playbook",
        "playbook_path": "playbooks/site.yml",
        "policy": {"allowed": True, "findings": [], "mode": "deny", "schema_version": 1},
        "requested_revision": "main",
        "resolved_revision": "abc123",
        "schema_version": 1,
        "targeting": {"limit": "web", "skip_tags": [], "tags": []},
        "verbosity": 1,
    }


class DeniedPreflightRunService(FakeRunService):
    def preflight(
        self,
        workspace_root: Path,
        playbook_identifier: Path,
        revision: str,
        policy_mode: EnforcementMode,
        mode: ExecutionMode,
        targeting: ExecutionTargeting,
        verbosity: int,
        diff: bool,
    ) -> RunPreflightResult:
        finding = PolicyFinding("RUN-001", "high", "Explicit limit required.", "playbooks/site.yml")
        return RunPreflightResult(
            PolicyReport((finding,), policy_mode),
            mode,
            "playbooks/site.yml",
            revision,
            "abc123",
            "sha256:inventory",
            "sha256:playbook",
            targeting,
            verbosity,
            diff,
        )


def test_run_preflight_human_denial_is_actionable(tmp_path: Path) -> None:
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
            "--apply",
            "--preflight",
        ],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        run_service=DeniedPreflightRunService(),  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_EXPECTED_FAILURE
    assert "Preflight: denied" in output.getvalue()
    assert "Mode: apply" in output.getvalue()
    assert "Requested revision: main" in output.getvalue()
    assert "Resolved revision: abc123" in output.getvalue()
    assert "Inventory digest: sha256:inventory" in output.getvalue()
    assert "Playbook digest: sha256:playbook" in output.getvalue()
    assert "Finding RUN-001: Explicit limit required." in output.getvalue()


def test_run_check_renders_injected_execution_result(tmp_path: Path) -> None:
    output = StringIO()

    result = main(
        [
            "--workspace",
            str(tmp_path),
            "--output-format",
            "json",
            "-vv",
            "run",
            "--playbook",
            "playbooks/site.yml",
            "--revision",
            "main",
            "--check",
            "--diff",
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
    assert json.loads(output.getvalue())["execution"]["verbosity"] == 2
    assert json.loads(output.getvalue())["execution"]["diff"] is True
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
        verbosity: int,
        diff: bool,
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


class CancelledRunService(FakeRunService):
    def run_check(
        self,
        workspace_root: Path,
        playbook_identifier: Path,
        revision: str,
        environment: object,
        timeout_seconds: float,
        policy_mode: EnforcementMode,
        targeting: ExecutionTargeting,
        verbosity: int,
        diff: bool,
    ) -> GovernedExecutionResult:
        return GovernedExecutionResult(
            PolicyReport((), policy_mode),
            ExecutionResult("run-cancelled", ExecutionStatus.CANCELLED, None, 0.1),
        )


def test_cancelled_run_uses_documented_exit_code_and_json_status(tmp_path: Path) -> None:
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
        ],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        run_service=CancelledRunService(),  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_CANCELLED
    assert json.loads(output.getvalue())["execution"]["status"] == "cancelled"


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
    assert "Next:" in error.getvalue()


def test_run_operational_failure_is_structured_in_json_mode(tmp_path: Path) -> None:
    output, error = StringIO(), StringIO()

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
            "--tags",
            "deploy,,config",
        ],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        run_service=FakeRunService(),  # type: ignore[arg-type]
        stdout=output,
        stderr=error,
    )

    assert result == EXIT_EXPECTED_FAILURE
    assert error.getvalue() == ""
    payload = json.loads(output.getvalue())
    assert payload["kind"] == "operational_failure"
    assert payload["operation"] == "run"
    assert "targeting values" in payload["reason"]
    assert payload["remediation"] == "Correct the run inputs or repository state and retry."


def test_run_workspace_failure_is_structured_in_json_mode(tmp_path: Path) -> None:
    output, error = StringIO(), StringIO()

    result = main(
        [
            "--output-format",
            "json",
            "run",
            "--playbook",
            "playbooks/site.yml",
            "--revision",
            "main",
            "--check",
        ],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        run_service=FakeRunService(),  # type: ignore[arg-type]
        stdout=output,
        stderr=error,
        current_directory=tmp_path,
    )

    assert result == EXIT_EXPECTED_FAILURE
    assert error.getvalue() == ""
    payload = json.loads(output.getvalue())
    assert payload["kind"] == "operational_failure"
    assert payload["operation"] == "run"
    assert payload["remediation"] == "Initialize or select a valid workspace and retry."


def test_run_apply_requires_confirmation_and_records_mode(tmp_path: Path) -> None:
    validation_output, validation_error = StringIO(), StringIO()
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
            stdout=validation_output,
            stderr=validation_error,
        )
        == EXIT_INVALID_INPUT
    )
    assert validation_error.getvalue() == ""
    assert json.loads(validation_output.getvalue()) == {
        "kind": "validation_failure",
        "operation": "run",
        "reason": "Apply execution requires --confirm.",
        "remediation": "Add --confirm, or use --preflight without executing.",
    }
    preflight_output = StringIO()
    preflight_result = main(
        [*arguments, "--preflight"],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        run_service=FakeRunService(),  # type: ignore[arg-type]
        stdout=preflight_output,
    )
    assert preflight_result == EXIT_SUCCESS
    assert json.loads(preflight_output.getvalue())["mode"] == "apply"
    output = StringIO()
    result = main(
        [*arguments, "--confirm"],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        run_service=FakeRunService(),  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_SUCCESS
    assert json.loads(output.getvalue())["execution"]["mode"] == "apply"


def test_run_apply_confirmation_validation_is_actionable_in_human_mode(tmp_path: Path) -> None:
    output, error = StringIO(), StringIO()

    result = main(
        [
            "--workspace",
            str(tmp_path),
            "run",
            "--playbook",
            "playbooks/site.yml",
            "--revision",
            "main",
            "--apply",
        ],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        run_service=FakeRunService(),  # type: ignore[arg-type]
        stdout=output,
        stderr=error,
    )

    assert result == EXIT_INVALID_INPUT
    assert output.getvalue() == ""
    assert "Apply execution requires --confirm" in error.getvalue()
    assert "use --preflight without executing" in error.getvalue()
    assert "Next:" in error.getvalue()


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
        verbosity: int,
        diff: bool,
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
        playbook_digest="sha256:playbook",
        playbook_path="playbooks/site.yml",
        verbosity=3,
        diff=True,
        operation="playbook.syntax_check",
    )

    def list(
        self,
        operation: str | None = None,
        status: ExecutionStatus | None = None,
        mode: ExecutionMode | None = None,
        inventory_digest: str | None = None,
        playbook_digest: str | None = None,
        resolved_revision: str | None = None,
        playbook_path: str | None = None,
        limit: int | None = None,
    ) -> tuple[ExecutionRecord, ...]:
        operation_matches = operation in {None, self.record.operation}
        status_matches = status in {None, self.record.status}
        mode_matches = mode in {None, self.record.mode}
        digest_matches = inventory_digest in {None, self.record.inventory_digest}
        playbook_matches = playbook_digest in {None, self.record.playbook_digest}
        revision_matches = resolved_revision in {None, self.record.resolved_revision}
        path_matches = playbook_path in {None, self.record.playbook_path}
        records = (
            (self.record,)
            if operation_matches
            and status_matches
            and mode_matches
            and digest_matches
            and playbook_matches
            and revision_matches
            and path_matches
            else ()
        )
        return records if limit is None else records[:limit]

    def get(self, execution_id: str) -> ExecutionRecord:
        if execution_id != self.record.execution_id:
            raise ExecutionError(f"Execution '{execution_id}' was not found in this workspace.")
        return self.record

    def summary(self) -> ExecutionSummary:
        return ExecutionSummary(
            1,
            {"completed": 1, "failed": 0, "timed_out": 0, "cancelled": 0},
            {"check": 1, "apply": 0},
            {"playbook.syntax_check": 1},
        )

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
    assert payload["executions"][0]["playbook_digest"] == "sha256:playbook"
    assert payload["executions"][0]["playbook_path"] == "playbooks/site.yml"
    assert payload["executions"][0]["verbosity"] == 3
    assert payload["executions"][0]["diff"] is True
    assert payload["executions"][0]["operation"] == "playbook.syntax_check"


def test_execution_summary_renders_safe_stable_counts(tmp_path: Path) -> None:
    output = StringIO()

    result = main(
        ["--workspace", str(tmp_path), "--output-format", "json", "execution", "summary"],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        execution_history_service=FakeExecutionHistoryService(),  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_SUCCESS
    assert json.loads(output.getvalue()) == {
        "by_mode": {"apply": 0, "check": 1},
        "by_operation": {"playbook.syntax_check": 1},
        "by_status": {"cancelled": 0, "completed": 1, "failed": 0, "timed_out": 0},
        "schema_version": 1,
        "total": 1,
    }


def test_execution_list_filters_by_exact_operation(tmp_path: Path) -> None:
    output = StringIO()

    result = main(
        [
            "--workspace",
            str(tmp_path),
            "--output-format",
            "json",
            "execution",
            "list",
            "--operation",
            "run",
        ],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        execution_history_service=FakeExecutionHistoryService(),  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_SUCCESS
    assert json.loads(output.getvalue())["executions"] == []


def test_execution_list_combines_operation_and_status_filters(tmp_path: Path) -> None:
    output = StringIO()

    result = main(
        [
            "--workspace",
            str(tmp_path),
            "--output-format",
            "json",
            "execution",
            "list",
            "--operation",
            "playbook.syntax_check",
            "--status",
            "completed",
            "--mode",
            "check",
            "--inventory-digest",
            "sha256:inventory",
            "--playbook-digest",
            "sha256:playbook",
            "--resolved-revision",
            "abc123",
            "--playbook-path",
            "playbooks/site.yml",
            "--limit",
            "1",
        ],
        workspace_service=FakeWorkspaceService(),  # type: ignore[arg-type]
        execution_history_service=FakeExecutionHistoryService(),  # type: ignore[arg-type]
        stdout=output,
    )

    assert result == EXIT_SUCCESS
    assert json.loads(output.getvalue())["executions"][0]["execution_id"] == "run-1"


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

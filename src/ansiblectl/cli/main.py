"""The ansiblectl console entry point."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from ansiblectl.application.execution import GovernedExecutionResult
from ansiblectl.application.execution_history import ExecutionHistoryService
from ansiblectl.application.inventory import InventoryService
from ansiblectl.application.plugins import PluginDiscoveryService
from ansiblectl.application.repository import RepositoryService
from ansiblectl.application.run import RunService
from ansiblectl.application.status import StatusService
from ansiblectl.application.workspace import WorkspaceService
from ansiblectl.cli.composition import (
    build_execution_history_service,
    build_inventory_service,
    build_plugin_discovery_service,
    build_repository_service,
    build_run_service,
    build_status_service,
    build_workspace_service,
    execution_environment,
)
from ansiblectl.domain.errors import ExecutionError, WorkspaceError
from ansiblectl.domain.execution import (
    ExecutionRecord,
    ExecutionRetentionResult,
    ExecutionStatus,
    ExecutionTargeting,
)
from ansiblectl.domain.inventory import InventoryError, ResolvedInventory
from ansiblectl.domain.playbook import PlaybookError
from ansiblectl.domain.plugins import PluginManifestError, ProviderDescriptor
from ansiblectl.domain.policy import EnforcementMode
from ansiblectl.domain.repository import RepositoryError, RepositoryRequest, RepositoryResult
from ansiblectl.domain.workspace import Workspace

EXIT_SUCCESS = 0
EXIT_EXPECTED_FAILURE = 1
EXIT_INVALID_INPUT = 2


@dataclass(frozen=True)
class CliOptions:
    """Global options resolved before a command invokes an application use case."""

    workspace: Path | None
    verbosity: int
    output_format: str
    non_interactive: bool


def build_parser() -> argparse.ArgumentParser:
    """Build the stable public command tree and its generated help."""

    parser = argparse.ArgumentParser(
        prog="ansiblectl", description="Manage Ansible automation safely."
    )
    parser.add_argument("--workspace", type=Path, help="Workspace directory for this operation.")
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="Increase diagnostic detail."
    )
    parser.add_argument(
        "--output-format",
        choices=("human", "json"),
        default="human",
        help="Render command results for people or automation.",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Fail instead of prompting for input.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("status", help="Show the local application status.")
    workspace = subcommands.add_parser(
        "workspace", help="Create and inspect Ansiblectl workspaces."
    )
    workspace_commands = workspace.add_subparsers(dest="workspace_command", required=True)
    initialize = workspace_commands.add_parser("init", help="Initialise a workspace.")
    initialize.add_argument(
        "path", type=Path, nargs="?", help="Workspace directory (default: current directory)."
    )
    workspace_commands.add_parser("show", help="Show the selected or discovered workspace.")
    inventory = subcommands.add_parser("inventory", help="Resolve and inspect inventory.")
    inventory_commands = inventory.add_subparsers(dest="inventory_command", required=True)
    inventory_show = inventory_commands.add_parser("show", help="Show the resolved inventory.")
    inventory_show.add_argument(
        "--source",
        type=Path,
        help="Inventory YAML path inside the workspace (default: inventory/hosts.yml).",
    )
    repository = subcommands.add_parser("repository", help="Inspect and synchronise repositories.")
    repository_commands = repository.add_subparsers(dest="repository_command", required=True)
    for command, help_text in (
        ("inspect", "Inspect repository state."),
        ("sync", "Synchronise a clean repository to a revision."),
    ):
        repository_command = repository_commands.add_parser(command, help=help_text)
        repository_command.add_argument("path", type=Path, help="Repository path in the workspace.")
        repository_command.add_argument(
            "--revision", required=True, help="Explicit Git revision for this operation."
        )
    plugin = subcommands.add_parser("plugin", help="Validate and list plugin manifests.")
    plugin_commands = plugin.add_subparsers(dest="plugin_command", required=True)
    plugin_validate = plugin_commands.add_parser("validate", help="Validate one manifest.")
    plugin_validate.add_argument("manifest", type=Path, help="Manifest path in the workspace.")
    plugin_list = plugin_commands.add_parser("list", help="List validated manifests.")
    plugin_list.add_argument(
        "--manifest",
        type=Path,
        action="append",
        required=True,
        help="Manifest path in the workspace; repeat for multiple plugins.",
    )
    run = subcommands.add_parser("run", help="Run a validated playbook through Ansible.")
    run.add_argument("--playbook", type=Path, required=True, help="Playbook path in the workspace.")
    run.add_argument("--revision", required=True, help="Explicit repository revision.")
    run.add_argument(
        "--inventory",
        type=Path,
        default=Path("inventory/hosts.yml"),
        help="Inventory YAML path in the workspace.",
    )
    run_mode = run.add_mutually_exclusive_group(required=True)
    run_mode.add_argument("--check", action="store_true", help="Predict changes in check mode.")
    run_mode.add_argument("--apply", action="store_true", help="Apply changes after confirmation.")
    run.add_argument(
        "--confirm", action="store_true", help="Explicitly confirm an apply-mode execution."
    )
    run.add_argument("--timeout", type=float, default=300.0, help="Positive timeout in seconds.")
    run.add_argument("--limit", help="Ansible host pattern to target.")
    run.add_argument(
        "--tags", action="append", default=[], help="Comma-separated task tags; repeatable."
    )
    run.add_argument(
        "--skip-tags", action="append", default=[], help="Comma-separated task tags to skip."
    )
    run.add_argument(
        "--policy-mode",
        choices=tuple(EnforcementMode),
        type=EnforcementMode,
        default=EnforcementMode.DENY,
        help="Policy enforcement mode (default: deny).",
    )
    execution = subcommands.add_parser("execution", help="Inspect previous executions.")
    execution_commands = execution.add_subparsers(dest="execution_command", required=True)
    execution_commands.add_parser("list", help="List completed executions newest first.")
    execution_show = execution_commands.add_parser("show", help="Show one completed execution.")
    execution_show.add_argument("execution_id", help="Exact execution identifier.")
    execution_prune = execution_commands.add_parser(
        "prune", help="Preview or apply execution-history retention."
    )
    execution_prune.add_argument(
        "--keep", type=int, required=True, help="Number of newest executions to retain."
    )
    execution_prune.add_argument(
        "--apply", action="store_true", help="Apply the plan; otherwise only preview it."
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    status_service: StatusService | None = None,
    workspace_service: WorkspaceService | None = None,
    inventory_service: InventoryService | None = None,
    repository_service: RepositoryService | None = None,
    plugin_service: PluginDiscoveryService | None = None,
    run_service: RunService | None = None,
    execution_history_service: ExecutionHistoryService | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    current_directory: Path | None = None,
) -> int:
    """Run a command and return its documented process exit code."""

    parser = build_parser()
    arguments = parser.parse_args(argv)
    options = CliOptions(
        workspace=arguments.workspace,
        verbosity=arguments.verbose,
        output_format=arguments.output_format,
        non_interactive=arguments.non_interactive,
    )
    if arguments.command == "status":
        status_service_instance = status_service or build_status_service()
        status = status_service_instance.get_status()
        _render_status(status.version, status.message, options.output_format, stdout)
    elif arguments.command == "workspace":
        workspace_service_instance = workspace_service or build_workspace_service()
        try:
            workspace = _run_workspace_command(
                arguments, options, workspace_service_instance, current_directory
            )
        except WorkspaceError as error:
            print(f"Workspace error: {error}", file=stderr)
            return EXIT_EXPECTED_FAILURE
        _render_workspace(workspace, options.output_format, stdout)
    elif arguments.command == "inventory":
        try:
            if inventory_service is None:
                workspace_service_instance = workspace_service or build_workspace_service()
                workspace = workspace_service_instance.resolve(
                    options.workspace, current_directory or Path.cwd()
                )
                inventory_service_instance = build_inventory_service(
                    workspace.root, arguments.source
                )
            else:
                inventory_service_instance = inventory_service
            inventory = inventory_service_instance.resolve()
        except WorkspaceError as error:
            print(f"Workspace error: {error}", file=stderr)
            return EXIT_EXPECTED_FAILURE
        except InventoryError as error:
            print(f"Inventory error: {error}", file=stderr)
            return EXIT_EXPECTED_FAILURE
        _render_inventory(inventory, options.output_format, stdout)
    elif arguments.command == "repository":
        workspace_service_instance = workspace_service or build_workspace_service()
        repository_service_instance = repository_service or build_repository_service()
        try:
            workspace = workspace_service_instance.resolve(
                options.workspace, current_directory or Path.cwd()
            )
            request = RepositoryRequest(
                workspace.root,
                (workspace.root / arguments.path).resolve(),
                arguments.revision,
            )
            if arguments.repository_command == "sync":
                print(
                    f"Synchronising repository {request.repository_path} "
                    f"to revision {request.revision}.",
                    file=stderr,
                )
                result = repository_service_instance.sync(request)
            else:
                result = repository_service_instance.inspect(request)
        except WorkspaceError as error:
            print(f"Workspace error: {error}", file=stderr)
            return EXIT_EXPECTED_FAILURE
        except RepositoryError as error:
            print(f"Repository error: {error}", file=stderr)
            return EXIT_EXPECTED_FAILURE
        _render_repository(result, options.output_format, stdout)
    elif arguments.command == "plugin":
        workspace_service_instance = workspace_service or build_workspace_service()
        plugin_service_instance = plugin_service or build_plugin_discovery_service()
        try:
            workspace = workspace_service_instance.resolve(
                options.workspace, current_directory or Path.cwd()
            )
            identifiers = (
                [arguments.manifest]
                if arguments.plugin_command == "validate"
                else arguments.manifest
            )
            locations = [_resolve_workspace_path(workspace.root, path) for path in identifiers]
            descriptors = plugin_service_instance.discover_files(locations)
        except WorkspaceError as error:
            print(f"Workspace error: {error}", file=stderr)
            return EXIT_EXPECTED_FAILURE
        except PluginManifestError as error:
            print(f"Plugin manifest error: {error}", file=stderr)
            return EXIT_EXPECTED_FAILURE
        _render_plugins(descriptors, options.output_format, stdout)
    elif arguments.command == "run":
        if arguments.apply != arguments.confirm:
            print("Run error: --apply and --confirm must be used together.", file=stderr)
            return EXIT_INVALID_INPUT
        workspace_service_instance = workspace_service or build_workspace_service()
        try:
            workspace = workspace_service_instance.resolve(
                options.workspace, current_directory or Path.cwd()
            )
            run_service_instance = run_service or build_run_service(
                workspace.root, arguments.inventory
            )
            targeting = ExecutionTargeting(
                arguments.limit,
                _tag_values(arguments.tags),
                _tag_values(arguments.skip_tags),
            )
            run_arguments = (
                workspace.root,
                arguments.playbook,
                arguments.revision,
                execution_environment(),
                arguments.timeout,
                arguments.policy_mode,
            )
            run_result = (
                run_service_instance.run_apply(
                    *run_arguments, confirmed=arguments.confirm, targeting=targeting
                )
                if arguments.apply
                else run_service_instance.run_check(*run_arguments, targeting=targeting)
            )
        except WorkspaceError as error:
            print(f"Workspace error: {error}", file=stderr)
            return EXIT_EXPECTED_FAILURE
        except (InventoryError, PlaybookError, ExecutionError, RepositoryError) as error:
            print(f"Run error: {error}", file=stderr)
            return EXIT_EXPECTED_FAILURE
        _render_run_result(run_result, options.output_format, stdout)
        if run_result.execution is None:
            return EXIT_EXPECTED_FAILURE
        if run_result.execution.status is not ExecutionStatus.COMPLETED:
            return EXIT_EXPECTED_FAILURE
    elif arguments.command == "execution":
        workspace_service_instance = workspace_service or build_workspace_service()
        try:
            workspace = workspace_service_instance.resolve(
                options.workspace, current_directory or Path.cwd()
            )
            history = execution_history_service or build_execution_history_service(workspace.root)
            records: tuple[ExecutionRecord, ...]
            if arguments.execution_command == "prune":
                retention = history.retention(arguments.keep, apply=arguments.apply)
                _render_execution_retention(retention, options.output_format, stdout)
                return EXIT_SUCCESS
            if arguments.execution_command == "show":
                records = (history.get(arguments.execution_id),)
            else:
                records = history.list()
        except WorkspaceError as error:
            print(f"Workspace error: {error}", file=stderr)
            return EXIT_EXPECTED_FAILURE
        except ExecutionError as error:
            print(f"Execution history error: {error}", file=stderr)
            return EXIT_EXPECTED_FAILURE
        _render_execution_records(
            records, arguments.execution_command == "show", options.output_format, stdout
        )
    return EXIT_SUCCESS


def _run_workspace_command(
    arguments: argparse.Namespace,
    options: CliOptions,
    service: WorkspaceService,
    current_directory: Path | None,
) -> Workspace:
    if arguments.workspace_command == "init":
        return service.initialize(arguments.path or options.workspace or Path.cwd())
    return service.resolve(options.workspace, current_directory or Path.cwd())


def _render_status(version: str, message: str, output_format: str, output: TextIO | None) -> None:
    """Render the application result only at the CLI boundary."""

    if output_format == "json":
        print(json.dumps({"version": version, "message": message}, sort_keys=True), file=output)
        return
    print(f"ansiblectl {version}: {message}", file=output)


def _render_workspace(workspace: Workspace, output_format: str, output: TextIO | None) -> None:
    """Render validated workspace details at the CLI boundary."""

    if output_format == "json":
        print(
            json.dumps(
                {
                    "metadata_path": str(workspace.metadata_path),
                    "root": str(workspace.root),
                    "schema_version": workspace.schema_version,
                },
                sort_keys=True,
            ),
            file=output,
        )
        return
    print(f"Workspace: {workspace.root}", file=output)
    print(f"Metadata: {workspace.metadata_path}", file=output)


def _render_inventory(
    inventory: ResolvedInventory, output_format: str, output: TextIO | None
) -> None:
    """Render the stable inventory result only at the CLI boundary."""

    if output_format == "json":
        print(
            json.dumps(
                {
                    **inventory.canonical(),
                    "diagnostics": list(inventory.diagnostics),
                    "provenance": dict(sorted(inventory.provenance.items())),
                },
                sort_keys=True,
            ),
            file=output,
        )
        return
    print(f"Hosts: {len(inventory.hosts)}", file=output)
    print(f"Groups: {len(inventory.groups)}", file=output)
    for diagnostic in inventory.diagnostics:
        print(f"Diagnostic: {diagnostic}", file=output)


def _render_repository(
    repository: RepositoryResult, output_format: str, output: TextIO | None
) -> None:
    """Render repository state at the CLI boundary."""

    if output_format == "json":
        print(
            json.dumps(
                {
                    "dirty": repository.dirty,
                    "repository_path": str(repository.repository_path),
                    "revision": repository.revision,
                },
                sort_keys=True,
            ),
            file=output,
        )
        return
    print(f"Repository: {repository.repository_path}", file=output)
    print(f"Revision: {repository.revision}", file=output)
    print(f"Dirty: {'yes' if repository.dirty else 'no'}", file=output)


def _resolve_workspace_path(workspace_root: Path, identifier: Path) -> Path:
    root = workspace_root.resolve()
    candidate = (
        (root / identifier).resolve() if not identifier.is_absolute() else identifier.resolve()
    )
    if not candidate.is_relative_to(root):
        raise PluginManifestError("Plugin manifest must remain inside the selected workspace.")
    return candidate


def _render_plugins(
    descriptors: dict[str, ProviderDescriptor], output_format: str, output: TextIO | None
) -> None:
    """Render validated descriptors without loading plugin code."""

    plugins = [
        {
            "capabilities": list(descriptor.capabilities),
            "configuration_schema": descriptor.configuration_schema,
            "identity": descriptor.identity,
            "permissions": list(descriptor.permissions),
            "sdk_compatibility": descriptor.sdk_compatibility,
            "source": descriptor.source,
            "version": descriptor.version,
        }
        for _, descriptor in sorted(descriptors.items())
    ]
    if output_format == "json":
        print(json.dumps({"plugins": plugins, "schema_version": 1}, sort_keys=True), file=output)
        return
    for plugin in plugins:
        print(f"{plugin['identity']} {plugin['version']} ({plugin['source']})", file=output)


def _render_run_result(
    result: GovernedExecutionResult, output_format: str, output: TextIO | None
) -> None:
    """Render policy findings and an optional classified execution result."""

    execution = result.execution
    record = (
        None
        if execution is None
        else {
            "diagnostic": execution.diagnostic,
            "elapsed_seconds": execution.elapsed_seconds,
            "execution_id": execution.execution_id,
            "exit_code": execution.exit_code,
            "status": execution.status.value,
            "stderr_reference": execution.stderr_reference,
            "stdout_reference": execution.stdout_reference,
            "targeting": _targeting_record(execution.targeting),
            "mode": execution.mode.value,
            "requested_revision": execution.requested_revision,
            "resolved_revision": execution.resolved_revision,
            "inventory_digest": execution.inventory_digest,
            "playbook_digest": execution.playbook_digest,
        }
    )
    if output_format == "json":
        print(
            json.dumps(
                {
                    "execution": record,
                    "policy": result.report.machine_output(),
                    "schema_version": 1,
                },
                sort_keys=True,
            ),
            file=output,
        )
        return
    print(f"Policy: {result.report.mode.value}", file=output)
    for finding in result.report.findings:
        print(f"Finding {finding.rule_id}: {finding.message} ({finding.location})", file=output)
    if execution is not None:
        print(f"Execution: {execution.execution_id}", file=output)
        print(f"Status: {execution.status.value}", file=output)
        print(f"Mode: {execution.mode.value}", file=output)
        if execution.requested_revision:
            print(f"Requested revision: {execution.requested_revision}", file=output)
        if execution.resolved_revision:
            print(f"Resolved revision: {execution.resolved_revision}", file=output)
        if execution.inventory_digest:
            print(f"Inventory digest: {execution.inventory_digest}", file=output)
        if execution.playbook_digest:
            print(f"Playbook digest: {execution.playbook_digest}", file=output)
        if execution.stdout_reference:
            print(f"Stdout: {execution.stdout_reference}", file=output)
        if execution.stderr_reference:
            print(f"Stderr: {execution.stderr_reference}", file=output)
        if execution.diagnostic:
            print(f"Diagnostic: {execution.diagnostic}", file=output)
        _render_targeting(execution.targeting, output)


def _render_execution_records(
    records: tuple[ExecutionRecord, ...], show_one: bool, output_format: str, output: TextIO | None
) -> None:
    payload = [_execution_record(record) for record in records]
    if output_format == "json":
        key = "execution" if show_one else "executions"
        value: object = payload[0] if show_one else payload
        print(json.dumps({key: value, "schema_version": 1}, sort_keys=True), file=output)
        return
    if not records:
        print("No executions recorded.", file=output)
        return
    for record in records:
        print(f"Execution: {record.execution_id}", file=output)
        print(f"Timestamp: {record.timestamp}", file=output)
        print(f"Status: {record.status.value}", file=output)
        print(f"Mode: {record.mode.value}", file=output)
        if record.requested_revision:
            print(f"Requested revision: {record.requested_revision}", file=output)
        if record.resolved_revision:
            print(f"Resolved revision: {record.resolved_revision}", file=output)
        if record.inventory_digest:
            print(f"Inventory digest: {record.inventory_digest}", file=output)
        if record.playbook_digest:
            print(f"Playbook digest: {record.playbook_digest}", file=output)
        if record.stdout_reference:
            print(f"Stdout: {record.stdout_reference}", file=output)
        if record.stderr_reference:
            print(f"Stderr: {record.stderr_reference}", file=output)
        if record.diagnostic:
            print(f"Diagnostic: {record.diagnostic}", file=output)
        _render_targeting(record.targeting, output)


def _execution_record(record: ExecutionRecord) -> dict[str, object]:
    return {
        "diagnostic": record.diagnostic,
        "elapsed_seconds": record.elapsed_seconds,
        "execution_id": record.execution_id,
        "exit_code": record.exit_code,
        "status": record.status.value,
        "stderr_reference": record.stderr_reference,
        "stdout_reference": record.stdout_reference,
        "timestamp": record.timestamp,
        "targeting": _targeting_record(record.targeting),
        "mode": record.mode.value,
        "requested_revision": record.requested_revision,
        "resolved_revision": record.resolved_revision,
        "inventory_digest": record.inventory_digest,
        "playbook_digest": record.playbook_digest,
    }


def _tag_values(values: list[str]) -> tuple[str, ...]:
    return tuple(tag.strip() for value in values for tag in value.split(","))


def _targeting_record(targeting: ExecutionTargeting) -> dict[str, object]:
    return {
        "limit": targeting.limit,
        "skip_tags": list(targeting.skip_tags),
        "tags": list(targeting.tags),
    }


def _render_targeting(targeting: ExecutionTargeting, output: TextIO | None) -> None:
    if targeting.limit is not None:
        print(f"Limit: {targeting.limit}", file=output)
    if targeting.tags:
        print(f"Tags: {','.join(targeting.tags)}", file=output)
    if targeting.skip_tags:
        print(f"Skip tags: {','.join(targeting.skip_tags)}", file=output)


def _render_execution_retention(
    result: ExecutionRetentionResult, output_format: str, output: TextIO | None
) -> None:
    payload = {
        "applied": result.applied,
        "removed_execution_ids": list(result.removed_execution_ids),
        "retained_count": result.retained_count,
        "schema_version": 1,
    }
    if output_format == "json":
        print(json.dumps(payload, sort_keys=True), file=output)
        return
    action = "Applied" if result.applied else "Preview"
    print(f"{action}: retain {result.retained_count} execution(s)", file=output)
    print(f"Remove: {len(result.removed_execution_ids)} execution(s)", file=output)
    for execution_id in result.removed_execution_ids:
        print(f"Execution: {execution_id}", file=output)

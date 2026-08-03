"""The ansiblectl console entry point."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import TextIO

from ansiblectl.application.configuration import ConfigurationService
from ansiblectl.application.execution import GovernedExecutionResult
from ansiblectl.application.execution_history import ExecutionHistoryService, ExecutionSummary
from ansiblectl.application.filesystem import FilesystemRecoveryService
from ansiblectl.application.inventory import (
    InventoryService,
    InventoryValidationResult,
    InventoryValidationService,
)
from ansiblectl.application.playbook import PlaybookValidationResult, PlaybookValidationService
from ansiblectl.application.plugins import (
    PluginDiscoveryService,
    PluginPermissionReport,
    PluginPermissionService,
)
from ansiblectl.application.repository import RepositoryService
from ansiblectl.application.run import RunPreflightResult, RunService
from ansiblectl.application.state import CacheEntrySummary, StateService
from ansiblectl.application.status import StatusService
from ansiblectl.application.workspace import WorkspaceService
from ansiblectl.cli.boundary import render_exception
from ansiblectl.cli.composition import (
    build_configuration_service,
    build_execution_history_service,
    build_filesystem_recovery_service,
    build_inventory_service,
    build_inventory_validation_service,
    build_playbook_validation_service,
    build_plugin_discovery_service,
    build_repository_service,
    build_run_service,
    build_state_service,
    build_status_service,
    build_workspace_service,
    execution_environment,
)
from ansiblectl.cli.outcomes import render_outcome
from ansiblectl.cli.rendering import render_success
from ansiblectl.domain.configuration import EffectiveConfiguration
from ansiblectl.domain.context import CommandContext, create_command_context
from ansiblectl.domain.errors import (
    AnsiblectlError,
    ConfigurationError,
    ExecutionError,
    ExternalToolError,
    FilesystemRecoveryError,
    InternalOperationalError,
    PluginError,
    StateError,
    UsageError,
    ValidationError,
    WorkspaceError,
)
from ansiblectl.domain.execution import (
    ExecutionMode,
    ExecutionRecord,
    ExecutionRetentionResult,
    ExecutionStatus,
    ExecutionTargeting,
)
from ansiblectl.domain.filesystem import FilesystemRecoveryResult
from ansiblectl.domain.inventory import (
    InventoryError,
    ResolvedInventory,
    canonical_inventory_digest,
)
from ansiblectl.domain.outcomes import CommandOutcome, OutcomeKind
from ansiblectl.domain.permissions import CAPABILITY_PERMISSIONS, PermissionDeniedError
from ansiblectl.domain.playbook import PlaybookError
from ansiblectl.domain.plugins import PluginManifestError, ProviderDescriptor
from ansiblectl.domain.policy import EnforcementMode
from ansiblectl.domain.repository import RepositoryError, RepositoryRequest, RepositoryResult
from ansiblectl.domain.results import CommandResult, CommandWarning
from ansiblectl.domain.state import StateInvalidationResult
from ansiblectl.domain.workspace import Workspace

EXIT_SUCCESS = 0
EXIT_EXPECTED_FAILURE = 1
EXIT_INVALID_INPUT = 2
EXIT_CANCELLED = 3
EXIT_UNEXPECTED_FAILURE = 1
_COMMANDS: dict[str, frozenset[str]] = {
    "config": frozenset({"show"}),
    "execution": frozenset({"list", "prune", "show", "summary"}),
    "inventory": frozenset({"show", "validate"}),
    "playbook": frozenset({"validate"}),
    "plugin": frozenset({"discover", "list", "permissions", "validate"}),
    "repository": frozenset({"inspect", "sync"}),
    "run": frozenset(),
    "state": frozenset({"invalidate", "recover", "show"}),
    "status": frozenset(),
    "workspace": frozenset({"init", "show"}),
}


def cli(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run the installed CLI behind a safe unexpected-failure boundary."""

    arguments = tuple(sys.argv[1:] if argv is None else argv)
    output_format = _requested_output_format(arguments)
    execution_arguments = _legacy_output_arguments(arguments, output_format)
    context = create_command_context(
        _requested_command_name(arguments),
        debug=_requested_debug(arguments),
        output_format=output_format,
        interactive="--non-interactive" not in arguments,
    )
    actual_stdout = sys.stdout if stdout is None else stdout
    actual_stderr = sys.stderr if stderr is None else stderr
    invalid_output_source = _invalid_output_source(arguments)
    if invalid_output_source is not None:
        return render_exception(
            context,
            UsageError(
                "Invalid output format.",
                hint="Choose one of: text, json, or yaml.",
                context={"source": invalid_output_source},
            ),
            actual_stdout,
            actual_stderr,
        )
    buffered_stdout = StringIO()
    command_stdout = buffered_stdout
    diagnostics = StringIO()
    try:
        with redirect_stderr(diagnostics), redirect_stdout(command_stdout):
            result = main(
                execution_arguments,
                stdout=command_stdout,
                stderr=diagnostics,
                propagate_errors=True,
            )
    except SystemExit as error:
        if error.code is None or error.code == EXIT_SUCCESS:
            if output_format in {"json", "yaml"}:
                return render_success(
                    context,
                    CommandResult(data={"help": buffered_stdout.getvalue()}),
                    actual_stdout,
                    actual_stderr,
                )
            actual_stdout.write(buffered_stdout.getvalue())
            actual_stderr.write(diagnostics.getvalue())
            return EXIT_SUCCESS
        if error.code == EXIT_INVALID_INPUT and output_format in {"json", "yaml"}:
            return render_exception(
                context,
                UsageError(
                    "Invalid command arguments.",
                    hint="Run ansiblectl --help.",
                    cause=error,
                ),
                actual_stdout,
                actual_stderr,
            )
        if error.code == EXIT_INVALID_INPUT:
            actual_stderr.write(diagnostics.getvalue())
            raise
        return render_exception(
            context,
            InternalOperationalError(
                "An unexpected internal error occurred.",
                hint="Run the command again with --debug and report the operation ID.",
                cause=error,
            ),
            actual_stdout,
            actual_stderr,
        )
    except KeyboardInterrupt as error:
        return render_exception(context, error, actual_stdout, actual_stderr)
    except Exception as error:
        return render_exception(context, error, actual_stdout, actual_stderr)
    if output_format == "text" and result == EXIT_CANCELLED:
        return render_exception(context, KeyboardInterrupt(), actual_stdout, actual_stderr)
    if output_format == "text":
        actual_stdout.write(buffered_stdout.getvalue())
        actual_stderr.write(diagnostics.getvalue())
        return result
    try:
        return _render_buffered_result(
            context,
            result,
            buffered_stdout.getvalue(),
            actual_stdout,
            actual_stderr,
        )
    except KeyboardInterrupt as error:
        return render_exception(context, error, actual_stdout, actual_stderr)
    except Exception as error:
        return render_exception(context, error, actual_stdout, actual_stderr)


def _requested_output_format(arguments: Sequence[str]) -> str:
    """Read only the global format switch without repeating full argument parsing."""

    for index, argument in enumerate(arguments):
        if argument == "--output" and index + 1 < len(arguments):
            return (
                arguments[index + 1] if arguments[index + 1] in {"text", "json", "yaml"} else "text"
            )
        if argument.startswith("--output="):
            value = argument.partition("=")[2]
            return value if value in {"text", "json", "yaml"} else "text"
    for index, argument in enumerate(arguments):
        if argument == "--output-format" and index + 1 < len(arguments):
            return "json" if arguments[index + 1] == "json" else "text"
        if argument == "--output-format=json":
            return "json"
    environment_value = os.environ.get("ANSIBLECTL_OUTPUT", "").strip().lower()
    return environment_value if environment_value in {"text", "json", "yaml"} else "text"


def _requested_command_name(arguments: Sequence[str]) -> str:
    """Return public command identity without retaining option or positional values."""

    skip_next = False
    for index, argument in enumerate(arguments):
        if skip_next:
            skip_next = False
            continue
        if argument in {"--output", "--output-format", "--workspace"}:
            skip_next = True
            continue
        if argument.startswith("-"):
            continue
        subcommands = _COMMANDS.get(argument)
        if subcommands is None:
            continue
        if subcommands and index + 1 < len(arguments) and arguments[index + 1] in subcommands:
            return f"{argument} {arguments[index + 1]}"
        return argument
    return "ansiblectl"


def _invalid_output_source(arguments: Sequence[str]) -> str | None:
    """Identify an invalid Phase 1 output source without retaining its value."""

    for index, argument in enumerate(arguments):
        if argument == "--output":
            if index + 1 >= len(arguments):
                return "command_line"
            return None if arguments[index + 1] in {"text", "json", "yaml"} else "command_line"
        if argument.startswith("--output="):
            value = argument.partition("=")[2]
            return None if value in {"text", "json", "yaml"} else "command_line"
    for argument in arguments:
        if argument == "--output-format" or argument.startswith("--output-format="):
            return None
    environment_value = os.environ.get("ANSIBLECTL_OUTPUT", "").strip().lower()
    if environment_value and environment_value not in {"text", "json", "yaml"}:
        return "environment"
    return None


def _legacy_output_arguments(arguments: tuple[str, ...], output_format: str) -> tuple[str, ...]:
    """Translate the Phase 1 output option to the legacy command renderer during migration."""

    translated: list[str] = []
    skip_next = False
    has_legacy_option = False
    has_phase_option = any(
        argument == "--output" or argument.startswith("--output=") for argument in arguments
    )
    for argument in arguments:
        if skip_next:
            skip_next = False
            continue
        if argument == "--output":
            skip_next = True
            continue
        if argument.startswith("--output="):
            continue
        if argument == "--output-format":
            if has_phase_option:
                skip_next = True
                continue
            has_legacy_option = True
        elif argument.startswith("--output-format="):
            if has_phase_option:
                continue
            has_legacy_option = True
        translated.append(argument)
    if output_format in {"json", "yaml"} and not has_legacy_option:
        return ("--output-format", "json", *translated)
    return tuple(translated)


def _render_buffered_result(
    context: CommandContext,
    exit_code: int,
    rendered: str,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Adapt one legacy JSON document to a versioned Phase 1 envelope."""

    if exit_code == EXIT_CANCELLED:
        return render_exception(context, KeyboardInterrupt(), stdout, stderr)
    if exit_code == EXIT_SUCCESS:
        data = json.loads(rendered)
        return render_success(
            context,
            CommandResult(
                data=data,
                changed=_legacy_result_changed(context.command_name, data),
                warnings=_legacy_result_warnings(context.command_name, data),
            ),
            stdout,
            stderr,
        )

    payload = json.loads(rendered)
    reason = payload.get("reason") or "The command could not be completed."
    remediation = payload.get("remediation")
    kind = payload.get("kind")
    if kind == OutcomeKind.VALIDATION_FAILURE:
        error: BaseException = ValidationError(
            str(reason), hint=str(remediation) if remediation else None
        )
    elif kind == OutcomeKind.CANCELLED:
        error = KeyboardInterrupt()
    else:
        error = _legacy_error_for_command(
            context.command_name,
            str(reason),
            str(remediation) if remediation else None,
        )
    return render_exception(context, error, stdout, stderr)


def _legacy_result_changed(command_name: str, payload: object) -> bool:
    """Infer mutation only from explicit structured legacy result fields."""

    if not isinstance(payload, Mapping):
        return False
    if payload.get("changed") is True:
        return True
    if command_name == "state invalidate":
        return payload.get("applied") is True and payload.get("existed") is True
    if command_name == "state recover":
        recovered = payload.get("transaction_ids")
        return payload.get("applied") is True and isinstance(recovered, list) and bool(recovered)
    if command_name == "execution prune":
        removed = payload.get("removed_execution_ids")
        return payload.get("applied") is True and isinstance(removed, list) and bool(removed)
    return False


def _legacy_result_warnings(command_name: str, payload: object) -> tuple[CommandWarning, ...]:
    """Lift explicit non-fatal legacy findings without parsing rendered text."""

    if not isinstance(payload, Mapping):
        return ()
    warning_fields = {
        "inventory show": ("diagnostics", "INVENTORY_DIAGNOSTIC"),
        "playbook validate": ("findings", "PLAYBOOK_FINDING"),
    }
    definition = warning_fields.get(command_name)
    if definition is None:
        return ()
    field, code = definition
    values = payload.get(field)
    if not isinstance(values, list):
        return ()
    return tuple(
        CommandWarning(code, value) for value in values if isinstance(value, str) and value.strip()
    )


def _legacy_error_for_command(command_name: str, message: str, hint: str | None) -> AnsiblectlError:
    """Map a legacy failure to its broad typed subsystem without parsing error text."""

    subsystem = command_name.partition(" ")[0]
    error_types: dict[str, type[AnsiblectlError]] = {
        "config": ConfigurationError,
        "execution": ExecutionError,
        "inventory": InventoryError,
        "playbook": PlaybookError,
        "plugin": PluginError,
        "repository": RepositoryError,
        "run": ExecutionError,
        "state": StateError,
        "workspace": WorkspaceError,
    }
    return error_types.get(subsystem, AnsiblectlError)(message, hint=hint)


def _requested_debug(arguments: Sequence[str]) -> bool:
    """Resolve debug mode before full argument parsing reaches the command boundary."""

    environment_value = os.environ.get("ANSIBLECTL_DEBUG", "").strip().lower()
    return "--debug" in arguments or environment_value in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class CliOptions:
    """Global options resolved before a command invokes an application use case."""

    workspace: Path | None
    verbosity: int
    output_format: str
    non_interactive: bool
    debug: bool


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
        "--debug",
        action="store_true",
        help="Include safe exception diagnostics when a command fails.",
    )
    parser.add_argument(
        "--output",
        choices=("text", "json", "yaml"),
        dest="phase_output_format",
        help="Render the public result as text, JSON, or YAML.",
    )
    parser.add_argument(
        "--output-format",
        choices=("human", "json"),
        default="human",
        help="Deprecated compatibility alias for human or JSON output.",
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
    config = subcommands.add_parser("config", help="Inspect effective configuration safely.")
    config_commands = config.add_subparsers(dest="config_command", required=True)
    config_commands.add_parser("show", help="Show redacted effective configuration.")
    state = subcommands.add_parser("state", help="Inspect workspace cache metadata safely.")
    state_commands = state.add_subparsers(dest="state_command", required=True)
    state_commands.add_parser("show", help="Show cache metadata without stored values.")
    state_invalidate = state_commands.add_parser(
        "invalidate", help="Preview or apply one exact cache-entry invalidation."
    )
    state_invalidate.add_argument("name", help="Exact cache-entry name.")
    state_invalidate.add_argument(
        "--apply", action="store_true", help="Apply invalidation; otherwise only preview it."
    )
    state_recover = state_commands.add_parser(
        "recover", help="Preview or recover interrupted filesystem transactions."
    )
    state_recover.add_argument(
        "--apply", action="store_true", help="Apply recovery; otherwise only preview it."
    )
    inventory = subcommands.add_parser("inventory", help="Resolve and inspect inventory.")
    inventory_commands = inventory.add_subparsers(dest="inventory_command", required=True)
    inventory_show = inventory_commands.add_parser("show", help="Show the resolved inventory.")
    inventory_show.add_argument(
        "--source",
        type=Path,
        help="Inventory YAML path inside the workspace (default: inventory/hosts.yml).",
    )
    inventory_validate = inventory_commands.add_parser(
        "validate", help="Validate the generated inventory through Ansible."
    )
    inventory_validate.add_argument(
        "--source",
        type=Path,
        help="Inventory YAML path inside the workspace (default: inventory/hosts.yml).",
    )
    inventory_validate.add_argument(
        "--timeout", type=float, default=300.0, help="Positive validation timeout in seconds."
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
    plugin_discover = plugin_commands.add_parser(
        "discover", help="Discover manifests in one workspace directory."
    )
    plugin_discover.add_argument(
        "--directory",
        type=Path,
        default=Path("plugins"),
        help="Manifest directory inside the workspace (default: plugins).",
    )
    plugin_permissions = plugin_commands.add_parser(
        "permissions", help="Preview permissions for one validated manifest."
    )
    plugin_permissions.add_argument("manifest", type=Path, help="Manifest path in the workspace.")
    plugin_permissions.add_argument(
        "--grant",
        action="append",
        default=[],
        choices=tuple(CAPABILITY_PERMISSIONS),
        help="Explicit policy grant; repeat for multiple permissions.",
    )
    playbook = subcommands.add_parser("playbook", help="Validate playbook selection.")
    playbook_commands = playbook.add_subparsers(dest="playbook_command", required=True)
    playbook_validate = playbook_commands.add_parser(
        "validate", help="Validate a playbook without executing it."
    )
    playbook_validate.add_argument("path", type=Path, help="Playbook path in the workspace.")
    playbook_validate.add_argument(
        "--revision", required=True, help="Explicit repository revision."
    )
    playbook_validate.add_argument(
        "--syntax-check",
        action="store_true",
        help="Run ansible-playbook --syntax-check after selection validation.",
    )
    playbook_validate.add_argument(
        "--timeout", type=float, default=300.0, help="Positive syntax-check timeout in seconds."
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
    run.add_argument(
        "--preflight",
        action="store_true",
        help="Validate inputs and policy without starting Ansible.",
    )
    run.add_argument("--timeout", type=float, default=300.0, help="Positive timeout in seconds.")
    run.add_argument(
        "--diff", action="store_true", help="Show Ansible before-and-after differences."
    )
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
    execution_list = execution_commands.add_parser(
        "list", help="List completed executions newest first."
    )
    execution_list.add_argument(
        "--operation", help="Show only records with this exact operation identifier."
    )
    execution_list.add_argument(
        "--status",
        choices=tuple(ExecutionStatus),
        type=ExecutionStatus,
        help="Show only records with this classified status.",
    )
    execution_list.add_argument(
        "--mode",
        choices=tuple(ExecutionMode),
        type=ExecutionMode,
        help="Show only check-mode or apply-mode records.",
    )
    execution_list.add_argument(
        "--inventory-digest",
        help="Show only records with this exact canonical inventory digest.",
    )
    execution_list.add_argument(
        "--playbook-digest",
        help="Show only records with this exact validated playbook digest.",
    )
    execution_list.add_argument(
        "--resolved-revision",
        help="Show only records attributed to this immutable Git object identifier.",
    )
    execution_list.add_argument(
        "--playbook-path",
        help="Show only records for this workspace-relative POSIX playbook path.",
    )
    execution_list.add_argument(
        "--limit", type=int, help="Return at most this many newest matching records."
    )
    execution_commands.add_parser(
        "summary", help="Summarise safe execution metadata by status, mode, and operation."
    )
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
    configuration_service: ConfigurationService | None = None,
    state_service: StateService | None = None,
    filesystem_recovery_service: FilesystemRecoveryService | None = None,
    inventory_service: InventoryService | None = None,
    inventory_validation_service: InventoryValidationService | None = None,
    repository_service: RepositoryService | None = None,
    plugin_service: PluginDiscoveryService | None = None,
    plugin_permission_service: PluginPermissionService | None = None,
    playbook_service: PlaybookValidationService | None = None,
    run_service: RunService | None = None,
    execution_history_service: ExecutionHistoryService | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    current_directory: Path | None = None,
    propagate_errors: bool = False,
) -> int:
    """Run a command and return its documented process exit code."""

    parser = build_parser()
    arguments = parser.parse_args(argv)
    output_format = arguments.output_format
    if arguments.phase_output_format is not None:
        output_format = "human" if arguments.phase_output_format == "text" else "json"
    options = CliOptions(
        workspace=arguments.workspace,
        verbosity=arguments.verbose,
        output_format=output_format,
        non_interactive=arguments.non_interactive,
        debug=arguments.debug,
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
            if propagate_errors:
                raise
            return _render_cli_failure(
                f"workspace {arguments.workspace_command}",
                str(error),
                "Initialize or select a valid workspace and retry.",
                options.output_format,
                stdout,
                stderr,
            )
        _render_workspace(workspace, options.output_format, stdout)
    elif arguments.command == "config":
        workspace_service_instance = workspace_service or build_workspace_service()
        try:
            workspace = workspace_service_instance.resolve(
                options.workspace, current_directory or Path.cwd()
            )
            configuration_service_instance = configuration_service or build_configuration_service(
                workspace
            )
            configuration = configuration_service_instance.resolve()
        except WorkspaceError as error:
            if propagate_errors:
                raise
            return _render_cli_failure(
                "config show",
                str(error),
                "Initialize or select a valid workspace and retry.",
                options.output_format,
                stdout,
                stderr,
            )
        except ConfigurationError as error:
            if propagate_errors:
                raise
            return _render_cli_failure(
                "config show",
                str(error),
                "Correct the identified configuration source and retry.",
                options.output_format,
                stdout,
                stderr,
            )
        _render_configuration(configuration, options.output_format, stdout)
    elif arguments.command == "state":
        workspace_service_instance = workspace_service or build_workspace_service()
        state_operation = f"state {arguments.state_command}"
        try:
            workspace = workspace_service_instance.resolve(
                options.workspace, current_directory or Path.cwd()
            )
            state_service_instance = state_service or build_state_service(workspace.root)
            if arguments.state_command == "invalidate":
                invalidation = state_service_instance.invalidate(
                    arguments.name, apply=arguments.apply
                )
            elif arguments.state_command == "recover":
                recovery_service = filesystem_recovery_service or build_filesystem_recovery_service(
                    workspace.root
                )
                recovery = recovery_service.recover(apply=arguments.apply)
            else:
                entries = state_service_instance.inspect()
        except WorkspaceError as error:
            if propagate_errors:
                raise
            return _render_cli_failure(
                state_operation,
                str(error),
                "Initialize or select a valid workspace and retry.",
                options.output_format,
                stdout,
                stderr,
            )
        except StateError as error:
            if propagate_errors:
                raise
            return _render_cli_failure(
                state_operation,
                str(error),
                "Reset the identified state file and retry.",
                options.output_format,
                stdout,
                stderr,
            )
        except FilesystemRecoveryError as error:
            if propagate_errors:
                raise
            return _render_cli_failure(
                state_operation,
                str(error),
                "Inspect the retained transaction journal and retry recovery.",
                options.output_format,
                stdout,
                stderr,
            )
        if arguments.state_command == "invalidate":
            _render_state_invalidation(invalidation, options.output_format, stdout)
        elif arguments.state_command == "recover":
            _render_filesystem_recovery(recovery, options.output_format, stdout)
        else:
            _render_state(entries, options.output_format, stdout)
    elif arguments.command == "inventory":
        try:
            if arguments.inventory_command == "validate":
                workspace_service_instance = workspace_service or build_workspace_service()
                workspace = workspace_service_instance.resolve(
                    options.workspace, current_directory or Path.cwd()
                )
                validation_service = (
                    inventory_validation_service
                    or build_inventory_validation_service(workspace.root, arguments.source)
                )
                inventory_validation = validation_service.validate(
                    workspace.root,
                    execution_environment(workspace.root),
                    arguments.timeout,
                )
            elif inventory_service is None:
                workspace_service_instance = workspace_service or build_workspace_service()
                workspace = workspace_service_instance.resolve(
                    options.workspace, current_directory or Path.cwd()
                )
                inventory_service_instance = build_inventory_service(
                    workspace.root, arguments.source
                )
                inventory = inventory_service_instance.resolve()
            else:
                inventory_service_instance = inventory_service
                inventory = inventory_service_instance.resolve()
        except WorkspaceError as error:
            if propagate_errors:
                raise
            return _render_cli_failure(
                f"inventory {arguments.inventory_command}",
                str(error),
                "Initialize or select a valid workspace and retry.",
                options.output_format,
                stdout,
                stderr,
            )
        except (ExecutionError, InventoryError) as error:
            if propagate_errors:
                raise
            return _render_cli_failure(
                f"inventory {arguments.inventory_command}",
                str(error),
                "Correct the inventory source and retry.",
                options.output_format,
                stdout,
                stderr,
            )
        if arguments.inventory_command == "validate":
            if (
                propagate_errors
                and inventory_validation.execution.status is not ExecutionStatus.COMPLETED
            ):
                raise ExternalToolError(
                    "Inventory validation did not complete successfully.",
                    hint="Review the referenced validator diagnostics and correct the inventory.",
                    context={"status": inventory_validation.execution.status.value},
                )
            _render_inventory_validation(inventory_validation, options.output_format, stdout)
            if inventory_validation.execution.status is not ExecutionStatus.COMPLETED:
                return EXIT_EXPECTED_FAILURE
        else:
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
                if options.output_format == "human":
                    print(
                        f"Synchronising repository {request.repository_path} "
                        f"to revision {request.revision}.",
                        file=stderr,
                    )
                result = repository_service_instance.sync(request)
            else:
                result = repository_service_instance.inspect(request)
        except WorkspaceError as error:
            if propagate_errors:
                raise
            return _render_cli_failure(
                f"repository {arguments.repository_command}",
                str(error),
                "Initialize or select a valid workspace and retry.",
                options.output_format,
                stdout,
                stderr,
            )
        except RepositoryError as error:
            if propagate_errors:
                raise
            return _render_cli_failure(
                f"repository {arguments.repository_command}",
                str(error),
                "Correct the repository path or revision and retry.",
                options.output_format,
                stdout,
                stderr,
            )
        _render_repository(result, options.output_format, stdout)
    elif arguments.command == "plugin":
        workspace_service_instance = workspace_service or build_workspace_service()
        plugin_service_instance = plugin_service or build_plugin_discovery_service()
        try:
            workspace = workspace_service_instance.resolve(
                options.workspace, current_directory or Path.cwd()
            )
            if arguments.plugin_command == "discover":
                directory = _resolve_plugin_directory(workspace.root, arguments.directory)
                descriptors = plugin_service_instance.discover_directory(directory)
            elif arguments.plugin_command == "permissions":
                location = _resolve_workspace_path(workspace.root, arguments.manifest)
                descriptors = plugin_service_instance.discover_files([location])
                if len(descriptors) != 1:
                    raise PluginManifestError(
                        "Permission preflight requires exactly one validated manifest."
                    )
                descriptor = next(iter(descriptors.values()))
                permission_service = plugin_permission_service or PluginPermissionService()
                permission_report = permission_service.evaluate(
                    descriptor, frozenset(arguments.grant)
                )
            else:
                identifiers = (
                    [arguments.manifest]
                    if arguments.plugin_command == "validate"
                    else arguments.manifest
                )
                locations = [_resolve_workspace_path(workspace.root, path) for path in identifiers]
                descriptors = plugin_service_instance.discover_files(locations)
        except WorkspaceError as error:
            if propagate_errors:
                raise
            return _render_cli_failure(
                f"plugin {arguments.plugin_command}",
                str(error),
                "Initialize or select a valid workspace and retry.",
                options.output_format,
                stdout,
                stderr,
            )
        except (PermissionDeniedError, PluginManifestError) as error:
            if propagate_errors:
                raise
            return _render_cli_failure(
                f"plugin {arguments.plugin_command}",
                str(error),
                "Correct the plugin manifest selection and retry.",
                options.output_format,
                stdout,
                stderr,
            )
        if arguments.plugin_command == "permissions":
            _render_plugin_permissions(permission_report, options.output_format, stdout)
        else:
            _render_plugins(descriptors, options.output_format, stdout)
    elif arguments.command == "playbook":
        workspace_service_instance = workspace_service or build_workspace_service()
        try:
            workspace = workspace_service_instance.resolve(
                options.workspace, current_directory or Path.cwd()
            )
            playbook_service_instance = playbook_service or build_playbook_validation_service(
                workspace.root
            )
            validation = playbook_service_instance.validate(
                workspace.root,
                arguments.path,
                arguments.revision,
                syntax_check=arguments.syntax_check,
                environment=execution_environment(workspace.root),
                timeout_seconds=arguments.timeout,
            )
        except WorkspaceError as error:
            if propagate_errors:
                raise
            return _render_cli_failure(
                "playbook validate",
                str(error),
                "Initialize or select a valid workspace and retry.",
                options.output_format,
                stdout,
                stderr,
            )
        except (PlaybookError, ExecutionError) as error:
            if propagate_errors:
                raise
            return _render_cli_failure(
                "playbook validate",
                str(error),
                "Select a readable YAML playbook inside the workspace and retry.",
                options.output_format,
                stdout,
                stderr,
            )
        if (
            validation.syntax_check is not None
            and validation.syntax_check.status is not ExecutionStatus.COMPLETED
        ):
            if propagate_errors:
                raise ExternalToolError(
                    "Playbook syntax validation did not complete successfully.",
                    hint="Review the referenced validator diagnostics and correct the playbook.",
                    context={"status": validation.syntax_check.status.value},
                )
            _render_playbook_validation(validation, options.output_format, stdout)
            return EXIT_EXPECTED_FAILURE
        _render_playbook_validation(validation, options.output_format, stdout)
    elif arguments.command == "run":
        if arguments.confirm and not arguments.apply:
            if propagate_errors:
                raise ValidationError(
                    "--confirm requires --apply.",
                    hint="Remove --confirm or select --apply.",
                )
            return render_outcome(
                CommandOutcome(
                    OutcomeKind.VALIDATION_FAILURE,
                    "run",
                    reason="--confirm requires --apply.",
                    remediation="Remove --confirm or select --apply.",
                ),
                options.output_format,
                sys.stdout if stdout is None else stdout,
                sys.stderr if stderr is None else stderr,
            )
        if arguments.apply and not arguments.preflight and not arguments.confirm:
            if propagate_errors:
                raise ValidationError(
                    "Apply execution requires --confirm.",
                    hint="Add --confirm, or use --preflight without executing.",
                )
            return render_outcome(
                CommandOutcome(
                    OutcomeKind.VALIDATION_FAILURE,
                    "run",
                    reason="Apply execution requires --confirm.",
                    remediation="Add --confirm, or use --preflight without executing.",
                ),
                options.output_format,
                sys.stdout if stdout is None else stdout,
                sys.stderr if stderr is None else stderr,
            )
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
            if arguments.preflight:
                preflight_result = run_service_instance.preflight(
                    workspace.root,
                    arguments.playbook,
                    arguments.revision,
                    arguments.policy_mode,
                    ExecutionMode.APPLY if arguments.apply else ExecutionMode.CHECK,
                    targeting=targeting,
                    verbosity=options.verbosity,
                    diff=arguments.diff,
                )
            else:
                run_arguments = (
                    workspace.root,
                    arguments.playbook,
                    arguments.revision,
                    lambda: execution_environment(workspace.root),
                    arguments.timeout,
                    arguments.policy_mode,
                )
                run_result = (
                    run_service_instance.run_apply(
                        *run_arguments,
                        confirmed=arguments.confirm,
                        targeting=targeting,
                        verbosity=options.verbosity,
                        diff=arguments.diff,
                    )
                    if arguments.apply
                    else run_service_instance.run_check(
                        *run_arguments,
                        targeting=targeting,
                        verbosity=options.verbosity,
                        diff=arguments.diff,
                    )
                )
        except WorkspaceError as error:
            if propagate_errors:
                raise
            return _render_cli_failure(
                "run",
                str(error),
                "Initialize or select a valid workspace and retry.",
                options.output_format,
                stdout,
                stderr,
            )
        except (
            ConfigurationError,
            InventoryError,
            PlaybookError,
            ExecutionError,
            RepositoryError,
        ) as error:
            if propagate_errors:
                raise
            return _render_cli_failure(
                "run",
                str(error),
                "Correct the run inputs or repository state and retry.",
                options.output_format,
                stdout,
                stderr,
            )
        if arguments.preflight:
            if propagate_errors and not preflight_result.report.allowed:
                raise PermissionDeniedError(
                    "Run preflight was denied by policy.",
                    hint="Resolve the reported policy findings and retry.",
                )
            _render_run_preflight(preflight_result, options.output_format, stdout)
            if not preflight_result.report.allowed:
                return EXIT_EXPECTED_FAILURE
            return EXIT_SUCCESS
        if propagate_errors and run_result.execution is None:
            raise PermissionDeniedError(
                "Run execution was denied by policy.",
                hint="Resolve the reported policy findings and retry.",
            )
        if (
            propagate_errors
            and run_result.execution is not None
            and run_result.execution.status
            not in {ExecutionStatus.COMPLETED, ExecutionStatus.CANCELLED}
        ):
            raise ExternalToolError(
                "Ansible execution did not complete successfully.",
                hint="Review the referenced execution diagnostics and retry.",
                context={
                    "status": run_result.execution.status.value,
                    "exit_code": run_result.execution.exit_code,
                },
            )
        _render_run_result(run_result, options.output_format, stdout)
        if run_result.execution is None:
            return EXIT_EXPECTED_FAILURE
        if run_result.execution.status is ExecutionStatus.CANCELLED:
            return EXIT_CANCELLED
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
            if arguments.execution_command == "summary":
                summary = history.summary()
                _render_execution_summary(summary, options.output_format, stdout)
                return EXIT_SUCCESS
            if arguments.execution_command == "show":
                records = (history.get(arguments.execution_id),)
            else:
                records = history.list(
                    arguments.operation,
                    arguments.status,
                    arguments.mode,
                    arguments.inventory_digest,
                    arguments.playbook_digest,
                    arguments.resolved_revision,
                    arguments.playbook_path,
                    arguments.limit,
                )
        except WorkspaceError as error:
            if propagate_errors:
                raise
            return _render_cli_failure(
                f"execution {arguments.execution_command}",
                str(error),
                "Initialize or select a valid workspace and retry.",
                options.output_format,
                stdout,
                stderr,
            )
        except ExecutionError as error:
            if propagate_errors:
                raise
            return _render_cli_failure(
                f"execution {arguments.execution_command}",
                str(error),
                "Correct the execution identifier or retention request and retry.",
                options.output_format,
                stdout,
                stderr,
            )
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


def _render_configuration(
    configuration: EffectiveConfiguration, output_format: str, output: TextIO | None
) -> None:
    payload = {**configuration.redacted(), "schema_version": 1}
    if output_format == "json":
        print(json.dumps(payload, sort_keys=True), file=output)
        return
    project_name = configuration.project_name or "<not set>"
    print(f"Project: {project_name}", file=output)
    print(f"Log level: {configuration.log_level}", file=output)
    print("Secrets:", file=output)
    for name in sorted(configuration.secret_references):
        print(f"  {name}: <redacted>", file=output)
    print("Provenance:", file=output)
    for field, origin in sorted(configuration.provenance.items()):
        print(f"  {field}: {origin}", file=output)


def _render_state(
    entries: tuple[CacheEntrySummary, ...], output_format: str, output: TextIO | None
) -> None:
    payload = [
        {
            "invalidation_condition": entry.invalidation_condition,
            "name": entry.name,
            "source_identity": entry.source_identity,
        }
        for entry in entries
    ]
    if output_format == "json":
        print(json.dumps({"entries": payload, "schema_version": 1}, sort_keys=True), file=output)
        return
    if not entries:
        print("No cache entries recorded.", file=output)
        return
    for entry in entries:
        print(f"Cache entry: {entry.name}", file=output)
        print(f"Source: {entry.source_identity}", file=output)
        print(f"Invalidation: {entry.invalidation_condition}", file=output)


def _render_state_invalidation(
    result: StateInvalidationResult, output_format: str, output: TextIO | None
) -> None:
    payload = {
        "applied": result.applied,
        "existed": result.existed,
        "name": result.name,
        "remaining_count": result.remaining_count,
        "schema_version": 1,
    }
    if output_format == "json":
        print(json.dumps(payload, sort_keys=True), file=output)
        return
    action = "Applied" if result.applied else "Preview"
    presence = "found" if result.existed else "not found"
    print(f"{action}: cache entry '{result.name}' {presence}.", file=output)
    print(f"Remaining entries: {result.remaining_count}", file=output)


def _render_filesystem_recovery(
    result: FilesystemRecoveryResult, output_format: str, output: TextIO | None
) -> None:
    payload = {
        "applied": result.applied,
        "schema_version": 1,
        "transaction_ids": list(result.transaction_ids),
    }
    if output_format == "json":
        print(json.dumps(payload, sort_keys=True), file=output)
        return
    action = "Recovered" if result.applied else "Pending"
    print(f"{action} filesystem transactions: {len(result.transaction_ids)}", file=output)
    for transaction_id in result.transaction_ids:
        print(f"  {transaction_id}", file=output)


def _render_inventory(
    inventory: ResolvedInventory, output_format: str, output: TextIO | None
) -> None:
    """Render the stable inventory result only at the CLI boundary."""

    canonical = inventory.canonical()
    digest = canonical_inventory_digest(canonical)
    if output_format == "json":
        print(
            json.dumps(
                {
                    **canonical,
                    "diagnostics": list(inventory.diagnostics),
                    "digest": digest,
                    "provenance": dict(sorted(inventory.provenance.items())),
                    "schema_version": 1,
                },
                sort_keys=True,
            ),
            file=output,
        )
        return
    print(f"Hosts: {len(inventory.hosts)}", file=output)
    print(f"Groups: {len(inventory.groups)}", file=output)
    print(f"Digest: {digest}", file=output)
    for diagnostic in inventory.diagnostics:
        print(f"Diagnostic: {diagnostic}", file=output)


def _render_inventory_validation(
    result: InventoryValidationResult, output_format: str, output: TextIO | None
) -> None:
    execution = result.execution
    payload = {
        "diagnostic": execution.diagnostic,
        "digest": result.digest,
        "elapsed_seconds": execution.elapsed_seconds,
        "execution_id": execution.execution_id,
        "exit_code": execution.exit_code,
        "schema_version": 1,
        "status": execution.status.value,
        "stderr_reference": execution.stderr_reference,
        "stdout_reference": execution.stdout_reference,
        "validator": "ansible-inventory --list",
    }
    if output_format == "json":
        print(json.dumps(payload, sort_keys=True), file=output)
        return
    print(f"Inventory digest: {result.digest}", file=output)
    print(f"Validator: {payload['validator']}", file=output)
    print(f"Status: {execution.status.value}", file=output)
    if execution.stdout_reference:
        print(f"Stdout: {execution.stdout_reference}", file=output)
    if execution.stderr_reference:
        print(f"Stderr: {execution.stderr_reference}", file=output)
    if execution.diagnostic:
        print(f"Diagnostic: {execution.diagnostic}", file=output)


def _render_repository(
    repository: RepositoryResult, output_format: str, output: TextIO | None
) -> None:
    """Render repository state at the CLI boundary."""

    if output_format == "json":
        print(
            json.dumps(
                {
                    "dirty": repository.dirty,
                    "head_revision": repository.head_revision,
                    "repository_path": str(repository.repository_path),
                    "resolved_revision": repository.resolved_revision,
                    "revision": repository.revision,
                },
                sort_keys=True,
            ),
            file=output,
        )
        return
    print(f"Repository: {repository.repository_path}", file=output)
    print(f"Revision: {repository.revision}", file=output)
    if repository.resolved_revision:
        print(f"Resolved revision: {repository.resolved_revision}", file=output)
    if repository.head_revision:
        print(f"HEAD revision: {repository.head_revision}", file=output)
    print(f"Dirty: {'yes' if repository.dirty else 'no'}", file=output)


def _resolve_workspace_path(workspace_root: Path, identifier: Path) -> Path:
    root = workspace_root.resolve()
    candidate = (
        (root / identifier).resolve() if not identifier.is_absolute() else identifier.resolve()
    )
    if not candidate.is_relative_to(root):
        raise PluginManifestError("Plugin manifest must remain inside the selected workspace.")
    return candidate


def _resolve_plugin_directory(workspace_root: Path, identifier: Path) -> Path:
    root = workspace_root.resolve()
    candidate = root / identifier if not identifier.is_absolute() else identifier
    if candidate.is_symlink():
        raise PluginManifestError("Plugin manifest directory must not be a symbolic link.")
    return _resolve_workspace_path(root, candidate)


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


def _render_plugin_permissions(
    report: PluginPermissionReport, output_format: str, output: TextIO | None
) -> None:
    payload = {
        "denied": list(report.denied),
        "granted": list(report.granted),
        "identity": report.identity,
        "requested": list(report.requested),
        "schema_version": 1,
    }
    if output_format == "json":
        print(json.dumps(payload, sort_keys=True), file=output)
        return
    print(f"Plugin: {report.identity}", file=output)
    print(f"Requested: {','.join(report.requested) or '<none>'}", file=output)
    print(f"Granted: {','.join(report.granted) or '<none>'}", file=output)
    print(f"Denied: {','.join(report.denied) or '<none>'}", file=output)


def _render_playbook_validation(
    result: PlaybookValidationResult, output_format: str, output: TextIO | None
) -> None:
    payload = {
        "digest": result.digest,
        "findings": list(result.findings),
        "playbook_path": result.playbook_path,
        "revision": result.revision,
        "validator": result.validator,
        "validator_version": result.validator_version,
        "syntax_check": (
            None
            if result.syntax_check is None
            else {
                "diagnostic": result.syntax_check.diagnostic,
                "exit_code": result.syntax_check.exit_code,
                "status": result.syntax_check.status.value,
                "stderr_reference": result.syntax_check.stderr_reference,
                "stdout_reference": result.syntax_check.stdout_reference,
                "validator": result.syntax_check.validator,
            }
        ),
    }
    if output_format == "json":
        print(json.dumps(payload, sort_keys=True), file=output)
        return
    print(f"Playbook: {result.playbook_path}", file=output)
    print(f"Revision: {result.revision}", file=output)
    print(f"Digest: {result.digest}", file=output)
    print(f"Validator: {result.validator} {result.validator_version}", file=output)
    if result.syntax_check is not None:
        print(f"Syntax check: {result.syntax_check.status.value}", file=output)
        print(f"Syntax validator: {result.syntax_check.validator}", file=output)
        if result.syntax_check.stdout_reference:
            print(f"Stdout: {result.syntax_check.stdout_reference}", file=output)
        if result.syntax_check.stderr_reference:
            print(f"Stderr: {result.syntax_check.stderr_reference}", file=output)


def _render_run_preflight(
    result: RunPreflightResult, output_format: str, output: TextIO | None
) -> None:
    payload = {
        "diff": result.diff,
        "inventory_digest": result.inventory_digest,
        "mode": result.mode.value,
        "playbook_digest": result.playbook_digest,
        "playbook_path": result.playbook_path,
        "policy": result.report.machine_output(),
        "requested_revision": result.requested_revision,
        "resolved_revision": result.resolved_revision,
        "schema_version": 1,
        "targeting": _targeting_record(result.targeting),
        "verbosity": result.verbosity,
    }
    if output_format == "json":
        print(json.dumps(payload, sort_keys=True), file=output)
        return
    print(f"Preflight: {'allowed' if result.report.allowed else 'denied'}", file=output)
    print(f"Mode: {result.mode.value}", file=output)
    print(f"Playbook: {result.playbook_path}", file=output)
    print(f"Requested revision: {result.requested_revision}", file=output)
    if result.resolved_revision:
        print(f"Resolved revision: {result.resolved_revision}", file=output)
    print(f"Inventory digest: {result.inventory_digest}", file=output)
    print(f"Playbook digest: {result.playbook_digest}", file=output)
    for finding in result.report.findings:
        print(f"Finding {finding.rule_id}: {finding.message} ({finding.location})", file=output)
    _render_targeting(result.targeting, output)


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
            "playbook_path": execution.playbook_path,
            "verbosity": execution.verbosity,
            "diff": execution.diff,
            "operation": execution.operation,
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
        if execution.playbook_path:
            print(f"Playbook: {execution.playbook_path}", file=output)
        if execution.verbosity:
            print(f"Verbosity: {execution.verbosity}", file=output)
        if execution.diff:
            print("Diff: enabled", file=output)
        print(f"Operation: {execution.operation}", file=output)
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
        if record.playbook_path:
            print(f"Playbook: {record.playbook_path}", file=output)
        if record.verbosity:
            print(f"Verbosity: {record.verbosity}", file=output)
        if record.diff:
            print("Diff: enabled", file=output)
        print(f"Operation: {record.operation}", file=output)
        if record.stdout_reference:
            print(f"Stdout: {record.stdout_reference}", file=output)
        if record.stderr_reference:
            print(f"Stderr: {record.stderr_reference}", file=output)
        if record.diagnostic:
            print(f"Diagnostic: {record.diagnostic}", file=output)
        _render_targeting(record.targeting, output)


def _render_execution_summary(
    summary: ExecutionSummary, output_format: str, output: TextIO | None
) -> None:
    payload = {
        "by_mode": dict(summary.by_mode),
        "by_operation": dict(summary.by_operation),
        "by_status": dict(summary.by_status),
        "schema_version": 1,
        "total": summary.total,
    }
    if output_format == "json":
        print(json.dumps(payload, sort_keys=True), file=output)
        return
    print(f"Executions: {summary.total}", file=output)
    for status, count in summary.by_status.items():
        print(f"Status {status}: {count}", file=output)
    for mode, count in summary.by_mode.items():
        print(f"Mode {mode}: {count}", file=output)
    for operation, count in summary.by_operation.items():
        print(f"Operation {operation}: {count}", file=output)


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
        "playbook_path": record.playbook_path,
        "verbosity": record.verbosity,
        "diff": record.diff,
        "operation": record.operation,
    }


def _tag_values(values: list[str]) -> tuple[str, ...]:
    return tuple(tag.strip() for value in values for tag in value.split(","))


def _render_cli_failure(
    operation: str,
    reason: str,
    remediation: str,
    output_format: str,
    stdout: TextIO | None,
    stderr: TextIO | None,
) -> int:
    """Render one expected operational failure through the typed CLI contract."""

    return render_outcome(
        CommandOutcome(
            OutcomeKind.OPERATIONAL_FAILURE,
            operation,
            reason=reason,
            remediation=remediation,
        ),
        output_format,
        sys.stdout if stdout is None else stdout,
        sys.stderr if stderr is None else stderr,
    )


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

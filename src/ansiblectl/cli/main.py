"""The ansiblectl console entry point."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from ansiblectl.application.status import StatusService
from ansiblectl.application.workspace import WorkspaceService
from ansiblectl.cli.composition import build_status_service, build_workspace_service
from ansiblectl.domain.errors import WorkspaceError
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
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    status_service: StatusService | None = None,
    workspace_service: WorkspaceService | None = None,
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

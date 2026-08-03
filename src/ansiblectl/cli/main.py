"""The ansiblectl console entry point."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from ansiblectl.application.status import StatusService
from ansiblectl.cli.composition import build_status_service

EXIT_SUCCESS = 0
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
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    status_service: StatusService | None = None,
    stdout: TextIO | None = None,
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
        service = status_service or build_status_service()
        status = service.get_status()
        _render_status(status.version, status.message, options.output_format, stdout)
    return EXIT_SUCCESS


def _render_status(version: str, message: str, output_format: str, output: TextIO | None) -> None:
    """Render the application result only at the CLI boundary."""

    if output_format == "json":
        print(json.dumps({"version": version, "message": message}, sort_keys=True), file=output)
        return
    print(f"ansiblectl {version}: {message}", file=output)

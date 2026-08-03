"""Local subprocess adapter with explicit argv, environment, and timeout policy."""

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from ansiblectl.domain.execution import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    elapsed_since,
)


@dataclass(frozen=True)
class LocalExecutionAdapter:
    """Execute a validated argument vector without shell interpolation."""

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Run the request and classify completion, timeout, cancellation, or startup failure."""

        started_at = monotonic()
        if request.cancel_requested:
            return ExecutionResult(
                request.execution_id,
                ExecutionStatus.CANCELLED,
                None,
                elapsed_since(started_at),
                diagnostic="Execution was cancelled before process start.",
                targeting=request.targeting,
                mode=request.mode,
                requested_revision=_requested_revision(request),
                resolved_revision=request.resolved_revision,
                inventory_digest=request.inventory_digest,
            )
        try:
            completed = subprocess.run(
                request.argv,
                cwd=request.working_directory,
                env=dict(request.environment),
                capture_output=True,
                check=False,
                shell=False,
                timeout=request.timeout_seconds,
                text=True,
            )
        except subprocess.TimeoutExpired as error:
            stdout_reference, stderr_reference, diagnostic = _persist_outputs(
                request, error.stdout, error.stderr
            )
            return ExecutionResult(
                request.execution_id,
                ExecutionStatus.TIMED_OUT,
                None,
                elapsed_since(started_at),
                stdout_reference,
                stderr_reference,
                _join_diagnostics("Execution exceeded its configured timeout.", diagnostic),
                request.targeting,
                request.mode,
                _requested_revision(request),
                request.resolved_revision,
                request.inventory_digest,
            )
        except OSError as error:
            return ExecutionResult(
                request.execution_id,
                ExecutionStatus.FAILED,
                None,
                elapsed_since(started_at),
                diagnostic=f"Execution could not start: {error.__class__.__name__}.",
                targeting=request.targeting,
                mode=request.mode,
                requested_revision=_requested_revision(request),
                resolved_revision=request.resolved_revision,
                inventory_digest=request.inventory_digest,
            )
        status = ExecutionStatus.COMPLETED if completed.returncode == 0 else ExecutionStatus.FAILED
        stdout_reference, stderr_reference, diagnostic = _persist_outputs(
            request, completed.stdout, completed.stderr
        )
        return ExecutionResult(
            request.execution_id,
            status,
            completed.returncode,
            elapsed_since(started_at),
            stdout_reference,
            stderr_reference,
            diagnostic,
            request.targeting,
            request.mode,
            _requested_revision(request),
            request.resolved_revision,
            request.inventory_digest,
        )


def _persist_outputs(
    request: ExecutionRequest, stdout: str | bytes | None, stderr: str | bytes | None
) -> tuple[str | None, str | None, str | None]:
    """Persist non-empty process streams privately and return opaque file references."""

    try:
        output_directory = _output_directory(request)
        return (
            _write_stream(output_directory / "stdout.log", stdout),
            _write_stream(output_directory / "stderr.log", stderr),
            None,
        )
    except OSError as error:
        return None, None, f"Execution output could not be persisted: {error.__class__.__name__}."


def _output_directory(request: ExecutionRequest) -> Path:
    directory_key = hashlib.sha256(request.execution_id.encode("utf-8")).hexdigest()
    private_root = request.working_directory / ".ansiblectl"
    runs_directory = private_root / "runs"
    output_directory = runs_directory / directory_key
    for directory in (private_root, runs_directory, output_directory):
        directory.mkdir(mode=0o700, exist_ok=True)
        directory.chmod(0o700)
    return output_directory


def _write_stream(path: Path, stream: str | bytes | None) -> str | None:
    if not stream:
        return None
    content = stream.decode("utf-8", errors="replace") if isinstance(stream, bytes) else stream
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output_file:
        output_file.write(content)
    path.chmod(0o600)
    return str(path)


def _join_diagnostics(primary: str, secondary: str | None) -> str:
    return primary if secondary is None else f"{primary} {secondary}"


def _requested_revision(request: ExecutionRequest) -> str | None:
    return None if request.selected_playbook is None else request.selected_playbook.revision

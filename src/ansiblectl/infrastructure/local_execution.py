"""Local subprocess adapter with explicit argv, environment, and timeout policy."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
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
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                request.execution_id,
                ExecutionStatus.TIMED_OUT,
                None,
                elapsed_since(started_at),
                diagnostic="Execution exceeded its configured timeout.",
            )
        except OSError as error:
            return ExecutionResult(
                request.execution_id,
                ExecutionStatus.FAILED,
                None,
                elapsed_since(started_at),
                diagnostic=f"Execution could not start: {error.__class__.__name__}.",
            )
        status = ExecutionStatus.COMPLETED if completed.returncode == 0 else ExecutionStatus.FAILED
        return ExecutionResult(
            request.execution_id, status, completed.returncode, elapsed_since(started_at)
        )

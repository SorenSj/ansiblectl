"""Typed process-execution contract, independent of Ansible internals."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from time import monotonic
from typing import Protocol
from uuid import uuid4

from ansiblectl.domain.errors import ExecutionError


class ExecutionStatus(StrEnum):
    """Classified lifecycle result for a requested execution."""

    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ExecutionRequest:
    """Validated process inputs; arguments are never a shell command string."""

    argv: tuple[str, ...]
    working_directory: Path
    environment: Mapping[str, str]
    timeout_seconds: float | None = None
    execution_id: str = field(default_factory=lambda: str(uuid4()))
    cancel_requested: bool = False

    def __post_init__(self) -> None:
        if not self.argv or any(not argument for argument in self.argv):
            raise ExecutionError("Execution arguments must be a non-empty argument vector.")
        if not self.working_directory.is_absolute():
            raise ExecutionError("Execution working directory must be an absolute validated path.")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ExecutionError("Execution timeout must be greater than zero.")


@dataclass(frozen=True)
class ExecutionResult:
    """Safe execution outcome with output references rather than raw output."""

    execution_id: str
    status: ExecutionStatus
    exit_code: int | None
    elapsed_seconds: float
    stdout_reference: str | None = None
    stderr_reference: str | None = None
    diagnostic: str | None = None


class ExecutionPort(Protocol):
    """Port for controlled external process execution."""

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Run or classify an execution request."""


def elapsed_since(started_at: float) -> float:
    """Return a non-negative elapsed duration for result construction."""

    return max(0.0, monotonic() - started_at)

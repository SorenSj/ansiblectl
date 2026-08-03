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
from ansiblectl.domain.playbook import PlaybookReference


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
    selected_playbook: PlaybookReference | None = None
    execution_id: str = field(default_factory=lambda: str(uuid4()))
    cancel_requested: bool = False

    def __post_init__(self) -> None:
        if not self.argv or any(not argument for argument in self.argv):
            raise ExecutionError("Execution arguments must be a non-empty argument vector.")
        if not self.working_directory.is_absolute():
            raise ExecutionError("Execution working directory must be an absolute validated path.")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ExecutionError("Execution timeout must be greater than zero.")

    @classmethod
    def for_playbook(
        cls,
        argv: tuple[str, ...],
        working_directory: Path,
        environment: Mapping[str, str],
        selected_playbook: PlaybookReference,
        timeout_seconds: float | None = None,
    ) -> ExecutionRequest:
        """Create a request that retains the validated canonical playbook and revision."""

        return cls(argv, working_directory, environment, timeout_seconds, selected_playbook)


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


@dataclass(frozen=True)
class ExecutionRecord:
    """Persisted safe execution metadata available for later inspection."""

    timestamp: str
    execution_id: str
    status: ExecutionStatus
    exit_code: int | None
    elapsed_seconds: float
    stdout_reference: str | None = None
    stderr_reference: str | None = None
    diagnostic: str | None = None


class ExecutionHistoryPort(Protocol):
    """Read safe persisted execution metadata for one workspace."""

    def list(self) -> tuple[ExecutionRecord, ...]: ...

    def get(self, execution_id: str) -> ExecutionRecord: ...


class ExecutionPort(Protocol):
    """Port for controlled external process execution."""

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Run or classify an execution request."""


def elapsed_since(started_at: float) -> float:
    """Return a non-negative elapsed duration for result construction."""

    return max(0.0, monotonic() - started_at)

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


class ExecutionMode(StrEnum):
    """Whether Ansible predicts or applies remote changes."""

    CHECK = "check"
    APPLY = "apply"


@dataclass(frozen=True)
class ExecutionTargeting:
    """Validated optional host and task selection for an execution."""

    limit: str | None = None
    tags: tuple[str, ...] = ()
    skip_tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        values = (() if self.limit is None else (self.limit,)) + self.tags + self.skip_tags
        if any(not value.strip() or "\x00" in value for value in values):
            raise ExecutionError("Execution targeting values must be non-empty and contain no NUL.")


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
    targeting: ExecutionTargeting = field(default_factory=ExecutionTargeting)
    mode: ExecutionMode = ExecutionMode.CHECK
    resolved_revision: str | None = None

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
        targeting: ExecutionTargeting | None = None,
        mode: ExecutionMode = ExecutionMode.CHECK,
        resolved_revision: str | None = None,
    ) -> ExecutionRequest:
        """Create a request that retains the validated canonical playbook and revision."""

        return cls(
            argv,
            working_directory,
            environment,
            timeout_seconds,
            selected_playbook,
            targeting=targeting or ExecutionTargeting(),
            mode=mode,
            resolved_revision=resolved_revision,
        )


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
    targeting: ExecutionTargeting = field(default_factory=ExecutionTargeting)
    mode: ExecutionMode = ExecutionMode.CHECK
    requested_revision: str | None = None
    resolved_revision: str | None = None


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
    targeting: ExecutionTargeting = field(default_factory=ExecutionTargeting)
    mode: ExecutionMode = ExecutionMode.CHECK
    requested_revision: str | None = None
    resolved_revision: str | None = None


@dataclass(frozen=True)
class ExecutionRetentionResult:
    """Safe summary of records selected for or removed by retention."""

    retained_count: int
    removed_execution_ids: tuple[str, ...]
    applied: bool


class ExecutionHistoryPort(Protocol):
    """Read safe persisted execution metadata for one workspace."""

    def list(self) -> tuple[ExecutionRecord, ...]: ...

    def get(self, execution_id: str) -> ExecutionRecord: ...

    def prune(self, keep: int) -> ExecutionRetentionResult: ...


class ExecutionPort(Protocol):
    """Port for controlled external process execution."""

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Run or classify an execution request."""


def elapsed_since(started_at: float) -> float:
    """Return a non-negative elapsed duration for result construction."""

    return max(0.0, monotonic() - started_at)

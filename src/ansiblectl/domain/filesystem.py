"""Contracts for explicit recovery of interrupted filesystem transactions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

MAX_RECOVERY_AGE_SECONDS = 315_360_000.0


class FilesystemCapabilityReason(StrEnum):
    """Stable reason codes for an unsupported transaction filesystem."""

    POSIX_REQUIRED = "POSIX_REQUIRED"
    CONTROL_PATH_UNSAFE = "CONTROL_PATH_UNSAFE"
    OWNER_PERMISSIONS_UNAVAILABLE = "OWNER_PERMISSIONS_UNAVAILABLE"
    ADVISORY_LOCKING_UNAVAILABLE = "ADVISORY_LOCKING_UNAVAILABLE"
    ATOMIC_REPLACE_UNAVAILABLE = "ATOMIC_REPLACE_UNAVAILABLE"
    FILE_SYNC_UNAVAILABLE = "FILE_SYNC_UNAVAILABLE"
    DIRECTORY_SYNC_UNAVAILABLE = "DIRECTORY_SYNC_UNAVAILABLE"
    CROSS_DEVICE_TARGET = "CROSS_DEVICE_TARGET"
    PROBE_CLEANUP_FAILED = "PROBE_CLEANUP_FAILED"
    CAPABILITY_PROBE_FAILED = "CAPABILITY_PROBE_FAILED"


class RecoveryAction(StrEnum):
    """Stable operator actions derived from private journal state."""

    NONE = "none"
    CLEANUP = "cleanup"
    ROLLBACK = "rollback"
    MANUAL_INSPECTION = "manual_inspection"


class RecoveryReason(StrEnum):
    """Stable, non-sensitive recovery diagnostic reasons."""

    ACTIVE_OWNER = "ACTIVE_OWNER"
    ROLLBACK_REQUIRED = "ROLLBACK_REQUIRED"
    CLEANUP_REQUIRED = "CLEANUP_REQUIRED"
    JOURNAL_UNREADABLE = "JOURNAL_UNREADABLE"
    JOURNAL_STATE_UNKNOWN = "JOURNAL_STATE_UNKNOWN"


@dataclass(frozen=True)
class RecoveryDiagnostic:
    """Safe diagnostic projection of one private transaction journal."""

    transaction_id: str
    state: str
    age_seconds: float | None
    action: RecoveryAction
    reasons: tuple[RecoveryReason, ...]
    active_owner: bool
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Recovery diagnostic schema version must be 1.")
        if not self.transaction_id.strip() or not self.state.strip():
            raise ValueError("Recovery diagnostic identifiers must be non-empty.")
        if self.age_seconds is not None and not 0 <= self.age_seconds <= MAX_RECOVERY_AGE_SECONDS:
            raise ValueError("Recovery diagnostic age must be bounded.")
        if not self.reasons:
            raise ValueError("Recovery diagnostic reasons must be non-empty.")


@dataclass(frozen=True)
class FilesystemCapabilityReport:
    """Safe, workspace-scoped transaction capability result."""

    supported: bool
    platform: str
    scope_id: str | None
    reasons: tuple[FilesystemCapabilityReason, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Filesystem capability schema version must be 1.")
        if not self.platform.strip():
            raise ValueError("Filesystem capability platform must be non-empty.")
        if self.supported != (not self.reasons):
            raise ValueError("Filesystem capability support must agree with its reasons.")
        if self.supported and self.scope_id is None:
            raise ValueError("Supported filesystem capability requires a scope identifier.")


class FilesystemRecoveryPort(Protocol):
    """Inspect and recover durable transaction journals."""

    def pending(self) -> tuple[str, ...]: ...

    def recover(self) -> object: ...

    def diagnostics(self) -> tuple[RecoveryDiagnostic, ...]: ...


@dataclass(frozen=True)
class FilesystemRecoveryResult:
    """Safe recovery plan or applied result."""

    transaction_ids: tuple[str, ...]
    applied: bool

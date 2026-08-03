"""Contracts for explicit recovery of interrupted filesystem transactions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class FilesystemRecoveryPort(Protocol):
    """Inspect and recover durable transaction journals."""

    def pending(self) -> tuple[str, ...]: ...

    def recover(self) -> object: ...


@dataclass(frozen=True)
class FilesystemRecoveryResult:
    """Safe recovery plan or applied result."""

    transaction_ids: tuple[str, ...]
    applied: bool

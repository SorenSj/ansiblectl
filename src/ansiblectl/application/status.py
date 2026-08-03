"""The initial status use case used to verify CLI composition."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Status:
    """A safe, machine-readable description of the local application."""

    version: str
    message: str


class StatusService(Protocol):
    """Port used by delivery adapters to query application status."""

    def get_status(self) -> Status:
        """Return the current application status without external side effects."""


@dataclass(frozen=True)
class DefaultStatusService:
    """Minimal core implementation until workspace-aware status is introduced."""

    version: str

    def get_status(self) -> Status:
        return Status(version=self.version, message="Ansiblectl is ready.")

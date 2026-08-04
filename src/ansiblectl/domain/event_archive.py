"""Canonical workspace event archive selection and target contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ansiblectl.domain.durable_events import DurableEventEnvelope

MAX_EVENT_ARCHIVE_SEQUENCE = 99_999_999_999_999_999_999
_ARCHIVE_ID_PATTERN = re.compile(r"[a-z][a-z0-9._-]{0,127}")


@dataclass(frozen=True, repr=False)
class WorkspaceEventArchiveTarget:
    """One validated archive-relative target whose representation omits its identity."""

    archive_id: str
    filename: str

    def __repr__(self) -> str:
        return "WorkspaceEventArchiveTarget(archive_id=<redacted>, filename=<redacted>)"


@dataclass(frozen=True, repr=False)
class WorkspaceEventArchive:
    """One canonical logical archive selection without a caller-controlled path."""

    archive_id: str

    def __post_init__(self) -> None:
        validate_event_archive_id(self.archive_id)

    def target_for(self, envelope: DurableEventEnvelope) -> WorkspaceEventArchiveTarget:
        """Bind one valid envelope to its only canonical archive-relative filename."""

        if not isinstance(envelope, DurableEventEnvelope):
            raise ValueError("Event archive target requires a durable event envelope.")
        if envelope.sequence > MAX_EVENT_ARCHIVE_SEQUENCE:
            raise ValueError("Event archive sequence exceeds the canonical filename bound.")
        filename = f"{envelope.sequence:020d}-{envelope.event_id}.json"
        return WorkspaceEventArchiveTarget(self.archive_id, filename)

    def __repr__(self) -> str:
        return "WorkspaceEventArchive(archive_id=<redacted>)"


def validate_event_archive_id(archive_id: object) -> str:
    """Return one canonical logical archive identifier or reject it."""

    if not isinstance(archive_id, str) or _ARCHIVE_ID_PATTERN.fullmatch(archive_id) is None:
        raise ValueError("Workspace event archive ID is not canonical.")
    return archive_id


__all__ = [
    "MAX_EVENT_ARCHIVE_SEQUENCE",
    "WorkspaceEventArchive",
    "WorkspaceEventArchiveTarget",
    "validate_event_archive_id",
]

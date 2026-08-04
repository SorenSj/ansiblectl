"""Canonical workspace Unix-socket selection and wire contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ansiblectl.domain.durable_events import (
    MAX_DURABLE_EVENT_DELIVERY_BYTES,
    DurableEventEnvelope,
)

UNIX_SOCKET_DEADLINE_SECONDS = 10
UNIX_SOCKET_ACK_BYTES = 31
_SOCKET_ID_PATTERN = re.compile(r"[a-z][a-z0-9._-]{0,127}")


@dataclass(frozen=True, repr=False)
class WorkspaceUnixSocketTarget:
    """One fixed workspace-relative socket target with a redacted representation."""

    socket_id: str
    filename: str

    def __repr__(self) -> str:
        return "WorkspaceUnixSocketTarget(socket_id=<redacted>, filename=<redacted>)"


@dataclass(frozen=True, repr=False)
class WorkspaceUnixSocketRequest:
    """One exact request frame and event-bound acknowledgement expectation."""

    frame: bytes
    acknowledgement: bytes

    def __repr__(self) -> str:
        return "WorkspaceUnixSocketRequest(frame=<redacted>, acknowledgement=<redacted>)"


@dataclass(frozen=True, repr=False)
class WorkspaceUnixSocket:
    """One canonical logical socket selection without a caller-controlled path."""

    socket_id: str

    def __post_init__(self) -> None:
        validate_unix_socket_id(self.socket_id)

    @property
    def target(self) -> WorkspaceUnixSocketTarget:
        """Return the only canonical workspace-relative socket filename."""

        return WorkspaceUnixSocketTarget(self.socket_id, f"{self.socket_id}.sock")

    def request_for(self, envelope: DurableEventEnvelope) -> WorkspaceUnixSocketRequest:
        """Create the exact bounded frame and event-bound acknowledgement bytes."""

        if not isinstance(envelope, DurableEventEnvelope):
            raise ValueError("Unix socket request requires a durable event envelope.")
        body = envelope.to_canonical_bytes()
        if not body or len(body) > MAX_DURABLE_EVENT_DELIVERY_BYTES:
            raise ValueError("Unix socket event payload exceeds the canonical delivery bound.")
        frame = len(body).to_bytes(4, byteorder="big", signed=False) + body
        acknowledgement = f"ACK {envelope.event_id}\n".encode("ascii")
        assert len(acknowledgement) == UNIX_SOCKET_ACK_BYTES
        return WorkspaceUnixSocketRequest(frame, acknowledgement)

    def __repr__(self) -> str:
        return "WorkspaceUnixSocket(socket_id=<redacted>)"


def validate_unix_socket_id(socket_id: object) -> str:
    """Return one canonical logical socket identifier or reject it."""

    if not isinstance(socket_id, str) or _SOCKET_ID_PATTERN.fullmatch(socket_id) is None:
        raise ValueError("Workspace Unix socket ID is not canonical.")
    return socket_id


__all__ = [
    "UNIX_SOCKET_ACK_BYTES",
    "UNIX_SOCKET_DEADLINE_SECONDS",
    "WorkspaceUnixSocket",
    "WorkspaceUnixSocketRequest",
    "WorkspaceUnixSocketTarget",
    "validate_unix_socket_id",
]

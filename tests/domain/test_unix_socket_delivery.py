"""Workspace Unix-socket selection and wire-contract tests."""

from dataclasses import replace

import pytest

from ansiblectl.domain.durable_events import (
    MAX_DURABLE_EVENT_DELIVERY_BYTES,
    DurableEventEnvelope,
)
from ansiblectl.domain.unix_socket_delivery import (
    UNIX_SOCKET_ACK_BYTES,
    UNIX_SOCKET_DEADLINE_SECONDS,
    WorkspaceUnixSocket,
    validate_unix_socket_id,
)


def envelope() -> DurableEventEnvelope:
    return DurableEventEnvelope(
        "00000000Z80000000000000000",
        7,
        "workspace.initialized",
        "2026-08-04T00:00:00.000000Z",
        None,
        {"project_name": "demo"},
    )


@pytest.mark.parametrize("socket_id", ["audit", "audit.primary", "a-1", "a_1", "a" * 128])
def test_socket_accepts_only_canonical_logical_identifiers(socket_id: str) -> None:
    selection = WorkspaceUnixSocket(socket_id)

    assert selection.socket_id == socket_id
    assert validate_unix_socket_id(socket_id) == socket_id
    assert selection.target.socket_id == socket_id
    assert selection.target.filename == f"{socket_id}.sock"
    assert socket_id not in repr(selection)
    assert socket_id not in repr(selection.target)


@pytest.mark.parametrize(
    "socket_id",
    [
        None,
        True,
        1,
        "",
        "Audit",
        "audit socket",
        "audit/socket",
        r"audit\socket",
        ".",
        "..",
        "../audit",
        "/audit",
        "audit/",
        "@audit",
        "åudit",
        "a\x00b",
        "a" * 129,
    ],
)
def test_socket_rejects_paths_and_noncanonical_identifiers(socket_id: object) -> None:
    with pytest.raises(ValueError, match="not canonical"):
        WorkspaceUnixSocket(socket_id)  # type: ignore[arg-type]


def test_socket_request_has_exact_big_endian_frame_and_event_bound_acknowledgement() -> None:
    event = envelope()
    body = event.to_canonical_bytes()

    request = WorkspaceUnixSocket("audit").request_for(event)

    assert request.frame[:4] == len(body).to_bytes(4, "big")
    assert request.frame[4:] == body
    assert request.acknowledgement == b"ACK 00000000Z80000000000000000\n"
    assert len(request.acknowledgement) == UNIX_SOCKET_ACK_BYTES == 31
    assert UNIX_SOCKET_DEADLINE_SECONDS == 10
    representation = repr(request)
    assert event.event_id not in representation
    assert "workspace.initialized" not in representation


def test_socket_request_rejects_non_envelopes_and_oversized_canonical_content() -> None:
    selection = WorkspaceUnixSocket("audit")

    with pytest.raises(ValueError, match="durable event envelope"):
        selection.request_for(object())  # type: ignore[arg-type]

    payload_size = MAX_DURABLE_EVENT_DELIVERY_BYTES
    oversized = replace(envelope(), payload={"value": "x" * payload_size})
    with pytest.raises(ValueError, match="exceeds"):
        selection.request_for(oversized)

"""Durable event envelope contract tests."""

from dataclasses import replace
from typing import Any

import pytest

from ansiblectl.domain.durable_events import DurableEventClaim, DurableEventEnvelope


def test_envelope_defensively_copies_payload_and_exposes_complete_schema() -> None:
    tags = ["one"]
    payload: dict[str, object] = {"execution_id": "one", "targeting": {"tags": tags}}
    envelope = DurableEventEnvelope(
        "00000000Z80000000000000000",
        1,
        "execution.completed",
        "2026-08-04T00:00:00.000000Z",
        None,
        payload,
    )
    payload["execution_id"] = "changed"
    tags.append("two")

    assert envelope.to_payload() == {
        "schema_version": 1,
        "event_id": "00000000Z80000000000000000",
        "sequence": 1,
        "name": "execution.completed",
        "occurred_at": "2026-08-04T00:00:00.000000Z",
        "operation_id": None,
        "payload": {"execution_id": "one", "targeting": {"tags": ["one"]}},
    }
    assert envelope.to_canonical_bytes() == (
        b'{"event_id":"00000000Z80000000000000000","name":"execution.completed",'
        b'"occurred_at":"2026-08-04T00:00:00.000000Z","operation_id":null,'
        b'"payload":{"execution_id":"one","targeting":{"tags":["one"]}},'
        b'"schema_version":1,"sequence":1}'
    )
    assert not envelope.to_canonical_bytes().endswith(b"\n")


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": 2},
        {"event_id": "invalid"},
        {"sequence": 0},
        {"sequence": True},
        {"name": "internal.event"},
        {"occurred_at": "2026-08-04"},
        {"operation_id": "invalid"},
        {"payload": {1: "value"}},
        {"payload": {"value": float("inf")}},
        {"payload": {"value": object()}},
    ],
)
def test_envelope_rejects_noncanonical_or_unsafe_fields(changes: dict[str, Any]) -> None:
    envelope = DurableEventEnvelope(
        "00000000Z80000000000000000",
        1,
        "execution.completed",
        "2026-08-04T00:00:00.000000Z",
        None,
        {},
    )

    with pytest.raises(ValueError):
        replace(envelope, **changes)


def test_claim_requires_canonical_identity_and_contains_envelope() -> None:
    envelope = DurableEventEnvelope(
        "00000000Z80000000000000000",
        1,
        "execution.completed",
        "2026-08-04T00:00:00.000000Z",
        None,
        {},
    )
    claim = DurableEventClaim(
        "webhook.primary",
        "00000000Z90000000000000000",
        "2026-08-04T00:00:30.000000Z",
        envelope,
    )

    assert claim.envelope is envelope
    for changes in (
        {"consumer_id": "Webhook Primary"},
        {"claim_token": "invalid"},
        {"lease_expires_at": "2026-08-04"},
        {"envelope": object()},
    ):
        with pytest.raises(ValueError):
            replace(claim, **changes)

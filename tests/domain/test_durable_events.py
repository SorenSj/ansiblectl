"""Durable event envelope contract tests."""

from dataclasses import replace
from typing import Any

import pytest

from ansiblectl.domain.durable_events import DurableEventEnvelope


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

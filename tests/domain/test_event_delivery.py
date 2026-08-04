"""Transport-neutral durable delivery contract tests."""

from dataclasses import replace
from typing import Any

import pytest

from ansiblectl.domain.event_delivery import (
    DeliveryOutcome,
    DeliveryOutcomeState,
    DeliveryRetryProfile,
    DeliveryRunResult,
    DeliveryRunState,
)


def test_delivery_result_exposes_only_versioned_safe_fields() -> None:
    result = DeliveryRunResult(
        "adapter",
        DeliveryRunState.FAILED,
        2,
        1,
        "00000000Z80000000000000000",
        3,
        "TEMPORARY_UNAVAILABLE",
    )

    assert result.to_payload() == {
        "schema_version": 1,
        "consumer_id": "adapter",
        "state": "failed",
        "delivered_count": 2,
        "failed_count": 1,
        "last_event_id": "00000000Z80000000000000000",
        "last_sequence": 3,
        "failure_reason": "TEMPORARY_UNAVAILABLE",
    }


def test_adapter_outcome_enforces_stable_failure_reason() -> None:
    assert DeliveryOutcome.success() == DeliveryOutcome(DeliveryOutcomeState.DELIVERED)
    assert DeliveryOutcome.failure("TEMPORARY_UNAVAILABLE") == DeliveryOutcome(
        DeliveryOutcomeState.FAILED, "TEMPORARY_UNAVAILABLE"
    )
    with pytest.raises(ValueError):
        DeliveryOutcome(DeliveryOutcomeState.DELIVERED, "FAILED")
    with pytest.raises(ValueError):
        DeliveryOutcome.failure("private detail")


@pytest.mark.parametrize(
    "changes",
    [
        {"max_attempts": 0},
        {"max_attempts": True},
        {"retry_delays": ()},
        {"retry_delays": (0,)},
        {"lease_seconds": 0},
    ],
)
def test_retry_profile_requires_positive_bounded_values(changes: dict[str, Any]) -> None:
    profile = DeliveryRetryProfile(3, (10, 30), 30)

    with pytest.raises(ValueError):
        replace(profile, **changes)

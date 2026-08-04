"""Bounded orchestration for transport-neutral durable event delivery."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from ansiblectl.domain.durable_events import DurableEventEnvelope
from ansiblectl.domain.event_delivery import (
    DeliveryOutcome,
    DeliveryOutcomeState,
    DeliveryRetryProfile,
    DeliveryRunResult,
    DeliveryRunState,
    DurableEventDeliveryStore,
    EventDeliveryAdapterPort,
)

ADAPTER_FAILURE = "ADAPTER_FAILURE"


@dataclass(frozen=True)
class EventDeliveryService:
    """Run one or a bounded number of ordered delivery attempts."""

    store: DurableEventDeliveryStore
    adapter: EventDeliveryAdapterPort
    retry: DeliveryRetryProfile
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    def step(self, consumer_id: str) -> DeliveryRunResult:
        """Attempt at most the exact next due event for one consumer."""

        now = self.clock()
        claim = self.store.claim_next(consumer_id, lease_seconds=self.retry.lease_seconds, now=now)
        if claim is None:
            return DeliveryRunResult(consumer_id, DeliveryRunState.IDLE, 0, 0, None, None, None)
        outcome = self._deliver(claim.envelope)
        if outcome.state is DeliveryOutcomeState.DELIVERED:
            self.store.acknowledge(
                consumer_id,
                sequence=claim.envelope.sequence,
                event_id=claim.envelope.event_id,
                claim_token=claim.claim_token,
            )
            return DeliveryRunResult(
                consumer_id,
                DeliveryRunState.DELIVERED,
                1,
                0,
                claim.envelope.event_id,
                claim.envelope.sequence,
                None,
            )
        assert outcome.failure_reason is not None
        self.store.record_failure(
            consumer_id,
            sequence=claim.envelope.sequence,
            event_id=claim.envelope.event_id,
            claim_token=claim.claim_token,
            reason_code=outcome.failure_reason,
            retry_delays=self.retry.retry_delays,
            max_attempts=self.retry.max_attempts,
            now=now,
        )
        return DeliveryRunResult(
            consumer_id,
            DeliveryRunState.FAILED,
            0,
            1,
            claim.envelope.event_id,
            claim.envelope.sequence,
            outcome.failure_reason,
        )

    def run(self, consumer_id: str, *, max_events: int) -> DeliveryRunResult:
        """Deliver until bounded, idle, or failed without sleeping or polling."""

        if not isinstance(max_events, int) or isinstance(max_events, bool) or max_events < 1:
            raise ValueError("Delivery batch bound must be a positive integer.")
        delivered_count = 0
        last_result: DeliveryRunResult | None = None
        last_event_id: str | None = None
        last_sequence: int | None = None
        for _ in range(max_events):
            result = self.step(consumer_id)
            delivered_count += result.delivered_count
            last_result = result
            if result.last_event_id is not None:
                last_event_id = result.last_event_id
                last_sequence = result.last_sequence
            if result.state is not DeliveryRunState.DELIVERED:
                break
        assert last_result is not None
        return DeliveryRunResult(
            consumer_id,
            last_result.state,
            delivered_count,
            last_result.failed_count,
            last_event_id,
            last_sequence,
            last_result.failure_reason,
        )

    def _deliver(self, envelope: DurableEventEnvelope) -> DeliveryOutcome:
        try:
            outcome: object = self.adapter.deliver(envelope)
            if not isinstance(outcome, DeliveryOutcome):
                return DeliveryOutcome.failure(ADAPTER_FAILURE)
            return outcome
        except Exception:
            return DeliveryOutcome.failure(ADAPTER_FAILURE)


__all__ = ["ADAPTER_FAILURE", "EventDeliveryService"]

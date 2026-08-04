"""Payload-free operator use cases for durable public-event delivery."""

from ansiblectl.domain.durable_events import (
    DurableConsumerRegistrationResult,
    DurableConsumerStatus,
    DurableEventActionResult,
    DurableEventOperationsPort,
    DurableEventRetentionResult,
    DurableEventRetryResult,
)


class EventOperationsService:
    """Coordinate exact, preview-first durable-event operator actions."""

    def __init__(self, port: DurableEventOperationsPort) -> None:
        self._port = port

    def register(
        self, consumer_id: str, *, start_sequence: int = 1
    ) -> DurableConsumerRegistrationResult:
        applied = self._port.register_consumer(consumer_id, start_sequence=start_sequence)
        return DurableConsumerRegistrationResult(consumer_id, start_sequence, applied)

    def inspect(self) -> tuple[DurableConsumerStatus, ...]:
        return self._port.inspect_consumers()

    def retry(self, consumer_id: str, *, sequence: int, event_id: str) -> DurableEventRetryResult:
        self._port.retry(consumer_id, sequence=sequence, event_id=event_id)
        return DurableEventRetryResult(consumer_id, sequence, event_id)

    def abandon(
        self, consumer_id: str, *, sequence: int, event_id: str, apply: bool = False
    ) -> DurableEventActionResult:
        return self._port.abandon(consumer_id, sequence=sequence, event_id=event_id, apply=apply)

    def retention(self, *, apply: bool = False) -> DurableEventRetentionResult:
        return self._port.retain(apply=apply)


__all__ = ["EventOperationsService"]

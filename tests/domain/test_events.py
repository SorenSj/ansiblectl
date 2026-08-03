"""Event publication contract tests."""

from ansiblectl.domain.events import Event, EventBus


def test_event_payload_is_redacted_and_optional_subscriber_failure_is_isolated() -> None:
    delivered: list[Event] = []

    def broken(event: Event) -> None:
        raise RuntimeError("nope")

    bus = EventBus([broken, delivered.append])
    bus.publish(Event("execution.completed", {"execution_id": "one", "token": "hidden"}))

    assert delivered[0].payload == {"execution_id": "one", "token": "<redacted>"}
    assert bus.diagnostics == ["Subscriber failed for execution.completed: RuntimeError."]

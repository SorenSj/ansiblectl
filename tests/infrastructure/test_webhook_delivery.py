"""Canonical bounded HTTPS webhook adapter tests."""

from dataclasses import dataclass, field

import pytest

from ansiblectl.domain.durable_events import DurableEventEnvelope
from ansiblectl.domain.event_delivery import DeliveryOutcomeState
from ansiblectl.domain.secrets import SecretMaterial, SecretReference
from ansiblectl.domain.webhooks import (
    WebhookDestination,
    WebhookEndpoint,
    WebhookRequest,
    parse_webhook_endpoints,
)
from ansiblectl.infrastructure.webhook_delivery import (
    AUTHENTICATION_UNAVAILABLE,
    DESTINATION_DENIED,
    PAYLOAD_TOO_LARGE,
    REMOTE_REJECTED,
    REMOTE_RETRYABLE,
    TRANSPORT_FAILURE,
    HttpsWebhookDeliveryAdapter,
)


class Resolver:
    def __init__(self, addresses: tuple[str, ...] = ("8.8.8.8",)) -> None:
        self.addresses = addresses
        self.calls = 0

    def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        self.calls += 1
        return self.addresses


@dataclass
class Transport:
    status: object = 204
    calls: list[tuple[WebhookEndpoint, WebhookDestination, WebhookRequest]] = field(
        default_factory=list
    )

    def post(
        self,
        endpoint: WebhookEndpoint,
        destination: WebhookDestination,
        request: WebhookRequest,
    ) -> int:
        self.calls.append((endpoint, destination, request))
        if isinstance(self.status, BaseException):
            raise self.status
        return self.status  # type: ignore[return-value]


@dataclass
class Secrets:
    value: str
    calls: list[SecretReference] = field(default_factory=list)

    def resolve(self, reference: SecretReference) -> SecretMaterial:
        self.calls.append(reference)
        return SecretMaterial(self.value)


def endpoint(*, authenticated: bool = False) -> WebhookEndpoint:
    definition: dict[str, object] = {
        "url": "https://hooks.example.test/events",
        "allowed_hostnames": ["hooks.example.test"],
    }
    if authenticated:
        definition["bearer_secret"] = "env:WEBHOOK_TOKEN"
    document = {"schema_version": 1, "endpoints": {"audit": definition}}
    return parse_webhook_endpoints(document, "test")["audit"]


def envelope(payload: dict[str, object] | None = None) -> DurableEventEnvelope:
    return DurableEventEnvelope(
        "00000000Z80000000000000000",
        7,
        "workspace.initialized",
        "2026-08-04T00:00:00.000000Z",
        None,
        payload or {"project_name": "demo"},
    )


def test_adapter_sends_one_canonical_bounded_request_with_fixed_headers() -> None:
    transport = Transport()
    adapter = HttpsWebhookDeliveryAdapter(endpoint(), Resolver(), transport)

    outcome = adapter.deliver(envelope())

    assert outcome.state is DeliveryOutcomeState.DELIVERED
    assert len(transport.calls) == 1
    sent_endpoint, destination, request = transport.calls[0]
    assert sent_endpoint.endpoint_id == "audit"
    assert destination.addresses == ("8.8.8.8",)
    assert request.body == (
        b'{"event_id":"00000000Z80000000000000000","name":"workspace.initialized",'
        b'"occurred_at":"2026-08-04T00:00:00.000000Z","operation_id":null,'
        b'"payload":{"project_name":"demo"},"schema_version":1,"sequence":7}'
    )
    assert dict(request.headers) == {
        "Content-Type": "application/json",
        "Idempotency-Key": "00000000Z80000000000000000",
        "User-Agent": "ansiblectl-webhook/1",
        "X-Ansiblectl-Event-Id": "00000000Z80000000000000000",
        "X-Ansiblectl-Event-Sequence": "7",
    }
    assert "project_name" not in repr(request)


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (408, REMOTE_RETRYABLE),
        (425, REMOTE_RETRYABLE),
        (429, REMOTE_RETRYABLE),
        (500, REMOTE_RETRYABLE),
        (599, REMOTE_RETRYABLE),
        (400, REMOTE_REJECTED),
        (404, REMOTE_REJECTED),
        (300, REMOTE_REJECTED),
        (99, TRANSPORT_FAILURE),
        (True, TRANSPORT_FAILURE),
    ],
)
def test_adapter_classifies_status_without_exposing_transport_detail(
    status: object, reason: str
) -> None:
    outcome = HttpsWebhookDeliveryAdapter(endpoint(), Resolver(), Transport(status)).deliver(
        envelope()
    )

    assert outcome.state is DeliveryOutcomeState.FAILED
    assert outcome.failure_reason == reason


def test_adapter_maps_destination_and_transport_failures_without_retrying() -> None:
    denied_transport = Transport()
    denied = HttpsWebhookDeliveryAdapter(
        endpoint(), Resolver(("127.0.0.1",)), denied_transport
    ).deliver(envelope())
    broken_transport = Transport(RuntimeError("private response body"))
    broken = HttpsWebhookDeliveryAdapter(endpoint(), Resolver(), broken_transport).deliver(
        envelope()
    )

    assert denied.failure_reason == DESTINATION_DENIED
    assert denied_transport.calls == []
    assert broken.failure_reason == TRANSPORT_FAILURE
    assert len(broken_transport.calls) == 1
    assert "private response body" not in repr(broken)


def test_tls_failure_is_reduced_to_transport_code_without_trust_detail() -> None:
    sentinel = "sentinel-policy /private/ca.pem CERTIFICATE issuer serial TLS alert"
    transport = Transport(RuntimeError(sentinel))

    outcome = HttpsWebhookDeliveryAdapter(endpoint(), Resolver(), transport).deliver(envelope())

    assert outcome.failure_reason == TRANSPORT_FAILURE
    assert len(transport.calls) == 1
    assert all(part not in repr(outcome) for part in sentinel.split())


def test_adapter_resolves_bearer_material_immediately_without_repr_leakage() -> None:
    transport = Transport()
    secrets = Secrets("credential-value")
    adapter = HttpsWebhookDeliveryAdapter(
        endpoint(authenticated=True), Resolver(), transport, secrets
    )

    outcome = adapter.deliver(envelope())

    assert outcome.state is DeliveryOutcomeState.DELIVERED
    assert [str(reference) for reference in secrets.calls] == ["env:WEBHOOK_TOKEN"]
    request = transport.calls[0][2]
    assert request.bearer_material is not None
    assert request.bearer_material.reveal_for_operation() == "credential-value"
    assert "credential-value" not in repr(request)


@pytest.mark.parametrize("value", ["", "unsafe\rvalue", "unsafe\nvalue"])
def test_adapter_rejects_unavailable_or_malformed_authentication_before_io(value: str) -> None:
    transport = Transport()
    resolver = Resolver()
    outcome = HttpsWebhookDeliveryAdapter(
        endpoint(authenticated=True), resolver, transport, Secrets(value)
    ).deliver(envelope())
    missing = HttpsWebhookDeliveryAdapter(
        endpoint(authenticated=True), resolver, transport
    ).deliver(envelope())

    assert outcome.failure_reason == AUTHENTICATION_UNAVAILABLE
    assert missing.failure_reason == AUTHENTICATION_UNAVAILABLE
    assert transport.calls == []
    assert resolver.calls == 0


def test_adapter_rejects_oversized_payload_before_resolution_or_transport() -> None:
    transport = Transport()
    outcome = HttpsWebhookDeliveryAdapter(endpoint(), Resolver(), transport).deliver(
        envelope({"value": "x" * 300_000})
    )

    assert outcome.failure_reason == PAYLOAD_TOO_LARGE
    assert transport.calls == []

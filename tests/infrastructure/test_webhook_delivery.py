"""Canonical bounded HTTPS webhook adapter tests."""

from dataclasses import dataclass, field
from pathlib import Path

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
from ansiblectl.infrastructure.secret_router import SecretProviderRouter
from ansiblectl.infrastructure.webhook_delivery import (
    AUTHENTICATION_UNAVAILABLE,
    DESTINATION_DENIED,
    PAYLOAD_TOO_LARGE,
    REMOTE_REJECTED,
    REMOTE_RETRYABLE,
    SIGNING_UNAVAILABLE,
    TRANSPORT_FAILURE,
    HttpsWebhookDeliveryAdapter,
)
from ansiblectl.infrastructure.workspace_file_secrets import WorkspaceFileSecretProvider


class Resolver:
    def __init__(self, addresses: tuple[str, ...] = ("8.8.8.8",)) -> None:
        self.addresses = addresses
        self.calls = 0

    def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        self.calls += 1
        return self.addresses


@dataclass
class Clock:
    values: list[object]
    calls: int = 0

    def now_unix_seconds(self) -> int:
        value = self.values[self.calls]
        self.calls += 1
        if isinstance(value, BaseException):
            raise value
        return value  # type: ignore[return-value]


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


@dataclass
class MappingSecrets:
    values: dict[str, str]
    calls: list[SecretReference] = field(default_factory=list)

    def resolve(self, reference: SecretReference) -> SecretMaterial:
        self.calls.append(reference)
        return SecretMaterial(self.values[reference.key])


def endpoint(
    *, authenticated: bool = False, signed: bool = False, timestamped: bool = False
) -> WebhookEndpoint:
    definition: dict[str, object] = {
        "url": "https://hooks.example.test/events",
        "allowed_hostnames": ["hooks.example.test"],
    }
    if authenticated:
        definition["bearer_secret"] = "env:WEBHOOK_TOKEN"
    if signed:
        definition["signature_secret"] = "env:WEBHOOK_SIGNING_KEY"
    if timestamped:
        definition["signature_secret"] = "env:WEBHOOK_SIGNING_KEY"
        definition["signature_version"] = 2
    document = {
        "schema_version": 5 if timestamped else 4 if signed else 1,
        "endpoints": {"audit": definition},
    }
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


def test_adapter_signs_exact_canonical_body_with_fixed_hmac_vector() -> None:
    transport = Transport()
    secrets = Secrets("0123456789abcdef0123456789abcdef")

    outcome = HttpsWebhookDeliveryAdapter(
        endpoint(signed=True), Resolver(), transport, secrets
    ).deliver(envelope())

    assert outcome.state is DeliveryOutcomeState.DELIVERED
    assert [str(reference) for reference in secrets.calls] == ["env:WEBHOOK_SIGNING_KEY"]
    request = transport.calls[0][2]
    assert request.headers["X-Ansiblectl-Signature"] == (
        "v1=9cd15a92d21aef0885ed87b07c1690c29a4ad1edef5913f584f46f6c2686e7c0"
    )
    assert "WEBHOOK_SIGNING_KEY" not in repr(request)
    assert "0123456789abcdef" not in repr(request)


def test_adapter_signs_timestamp_and_exact_body_with_fixed_v2_vector() -> None:
    transport = Transport()
    secrets = Secrets("0123456789abcdef0123456789abcdef")
    clock = Clock([0])

    outcome = HttpsWebhookDeliveryAdapter(
        endpoint(timestamped=True), Resolver(), transport, secrets, clock
    ).deliver(envelope())

    assert outcome.state is DeliveryOutcomeState.DELIVERED
    assert clock.calls == 1
    request = transport.calls[0][2]
    assert request.headers["X-Ansiblectl-Timestamp"] == "0"
    assert request.headers["X-Ansiblectl-Signature"] == (
        "v2=f0d22c4f3df989ad73de48c92f2f4eb8c15c3b79d4726d6ba7bb914cf2189c9c"
    )


@pytest.mark.parametrize(
    "value", [-1, 253_402_300_800, True, False, 1.5, "1", RuntimeError("private clock")]
)
def test_invalid_v2_clock_fails_before_dns(value: object) -> None:
    resolver = Resolver()
    transport = Transport()
    clock = Clock([value])

    outcome = HttpsWebhookDeliveryAdapter(
        endpoint(timestamped=True),
        resolver,
        transport,
        Secrets("0123456789abcdef0123456789abcdef"),
        clock,
    ).deliver(envelope())

    assert outcome.failure_reason == SIGNING_UNAVAILABLE
    assert clock.calls == 1
    assert resolver.calls == 0
    assert transport.calls == []


def test_v2_retry_reads_new_timestamp_with_stable_body_and_identity() -> None:
    transport = Transport()
    clock = Clock([1, 2])
    adapter = HttpsWebhookDeliveryAdapter(
        endpoint(timestamped=True),
        Resolver(),
        transport,
        Secrets("0123456789abcdef0123456789abcdef"),
        clock,
    )

    assert adapter.deliver(envelope()).state is DeliveryOutcomeState.DELIVERED
    assert adapter.deliver(envelope()).state is DeliveryOutcomeState.DELIVERED

    first, second = (call[2] for call in transport.calls)
    assert clock.calls == 2
    assert first.body == second.body
    assert first.headers["Idempotency-Key"] == second.headers["Idempotency-Key"]
    assert first.headers["X-Ansiblectl-Timestamp"] == "1"
    assert second.headers["X-Ansiblectl-Timestamp"] == "2"
    assert first.headers["X-Ansiblectl-Signature"] != second.headers["X-Ansiblectl-Signature"]


def test_v1_and_unsigned_delivery_never_read_clock() -> None:
    clock = Clock([RuntimeError("must not be called")])
    for selected in (endpoint(), endpoint(signed=True)):
        outcome = HttpsWebhookDeliveryAdapter(
            selected,
            Resolver(),
            Transport(),
            Secrets("0123456789abcdef0123456789abcdef"),
            clock,
        ).deliver(envelope())
        assert outcome.state is DeliveryOutcomeState.DELIVERED
    assert clock.calls == 0


def test_bearer_and_signing_secrets_are_resolved_once_before_dns() -> None:
    transport = Transport()
    resolver = Resolver()
    secrets = MappingSecrets(
        {
            "WEBHOOK_TOKEN": "bearer-credential",
            "WEBHOOK_SIGNING_KEY": "0123456789abcdef0123456789abcdef",
        }
    )

    outcome = HttpsWebhookDeliveryAdapter(
        endpoint(authenticated=True, signed=True), resolver, transport, secrets
    ).deliver(envelope())

    assert outcome.state is DeliveryOutcomeState.DELIVERED
    assert [str(reference) for reference in secrets.calls] == [
        "env:WEBHOOK_TOKEN",
        "env:WEBHOOK_SIGNING_KEY",
    ]
    assert resolver.calls == 1
    request = transport.calls[0][2]
    assert request.bearer_material is not None
    assert request.headers["X-Ansiblectl-Signature"].startswith("v1=")
    representation = repr(request)
    assert "bearer-credential" not in representation
    assert "0123456789abcdef" not in representation
    assert request.headers["X-Ansiblectl-Signature"] not in representation


def test_private_file_bearer_and_signing_material_resolve_before_dns(tmp_path: Path) -> None:
    private = tmp_path / ".ansiblectl"
    private.mkdir(mode=0o700)
    private.chmod(0o700)
    secrets_directory = private / "secrets"
    secrets_directory.mkdir(mode=0o700)
    secrets_directory.chmod(0o700)
    for name, value in {
        "WEBHOOK_TOKEN": "bearer-credential",
        "WEBHOOK_SIGNING_KEY": "0123456789abcdef0123456789abcdef",
    }.items():
        candidate = secrets_directory / name
        candidate.write_text(value, encoding="utf-8")
        candidate.chmod(0o600)
    configured = parse_webhook_endpoints(
        {
            "schema_version": 4,
            "endpoints": {
                "audit": {
                    "url": "https://hooks.example.test/events",
                    "allowed_hostnames": ["hooks.example.test"],
                    "bearer_secret": "file:WEBHOOK_TOKEN",
                    "signature_secret": "file:WEBHOOK_SIGNING_KEY",
                }
            },
        },
        "test",
    )["audit"]
    resolver = Resolver()
    transport = Transport()
    provider = WorkspaceFileSecretProvider(tmp_path)

    outcome = HttpsWebhookDeliveryAdapter(
        configured,
        resolver,
        transport,
        SecretProviderRouter({"file": provider}),
    ).deliver(envelope())

    assert outcome.state is DeliveryOutcomeState.DELIVERED
    assert resolver.calls == 1
    request = transport.calls[0][2]
    assert request.bearer_material is not None
    assert request.bearer_material.reveal_for_operation() == "bearer-credential"
    assert request.headers["X-Ansiblectl-Signature"].startswith("v1=")


def test_unchanged_event_and_key_produce_same_signature_per_retry_attempt() -> None:
    transport = Transport()
    secrets = Secrets("0123456789abcdef0123456789abcdef")
    adapter = HttpsWebhookDeliveryAdapter(endpoint(signed=True), Resolver(), transport, secrets)

    first = adapter.deliver(envelope())
    second = adapter.deliver(envelope())

    assert first.state is DeliveryOutcomeState.DELIVERED
    assert second.state is DeliveryOutcomeState.DELIVERED
    assert len(secrets.calls) == 2
    signatures = [call[2].headers["X-Ansiblectl-Signature"] for call in transport.calls]
    assert signatures[0] == signatures[1]


@pytest.mark.parametrize(
    "value",
    ["", "x" * 31, "x" * 257, "x" * 31 + "\n", "x" * 31 + "\x7f"],
)
def test_signing_failure_stops_before_dns_without_unsigned_fallback(value: str) -> None:
    resolver = Resolver()
    transport = Transport()

    outcome = HttpsWebhookDeliveryAdapter(
        endpoint(signed=True), resolver, transport, Secrets(value)
    ).deliver(envelope())

    assert outcome.failure_reason == SIGNING_UNAVAILABLE
    assert resolver.calls == 0
    assert transport.calls == []


def test_missing_signing_provider_stops_before_dns() -> None:
    resolver = Resolver()
    transport = Transport()

    outcome = HttpsWebhookDeliveryAdapter(endpoint(signed=True), resolver, transport).deliver(
        envelope()
    )

    assert outcome.failure_reason == SIGNING_UNAVAILABLE
    assert resolver.calls == 0
    assert transport.calls == []


def test_signing_provider_exception_is_redacted_and_not_retried() -> None:
    class BrokenSecrets:
        calls = 0

        def resolve(self, reference: SecretReference) -> SecretMaterial:
            self.calls += 1
            raise RuntimeError(
                "sentinel-reference sentinel-key sentinel-signature provider-internals"
            )

    secrets = BrokenSecrets()
    resolver = Resolver()
    transport = Transport()

    outcome = HttpsWebhookDeliveryAdapter(
        endpoint(signed=True), resolver, transport, secrets
    ).deliver(envelope())

    assert outcome.failure_reason == SIGNING_UNAVAILABLE
    assert secrets.calls == 1
    assert resolver.calls == 0
    assert transport.calls == []
    for sentinel in ("sentinel-reference", "sentinel-key", "sentinel-signature", "provider"):
        assert sentinel not in repr(outcome)


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

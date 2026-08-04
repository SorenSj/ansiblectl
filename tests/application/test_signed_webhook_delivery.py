"""End-to-end redaction tests for signed delivery and durable retry state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ansiblectl.application.event_delivery import EventDeliveryService
from ansiblectl.domain.event_delivery import DeliveryRetryProfile
from ansiblectl.domain.events import Event
from ansiblectl.domain.secrets import SecretMaterial, SecretReference
from ansiblectl.domain.webhooks import (
    WebhookDestination,
    WebhookEndpoint,
    WebhookRequest,
    parse_webhook_endpoints,
)
from ansiblectl.infrastructure.event_outbox import SqliteEventOutbox
from ansiblectl.infrastructure.webhook_delivery import (
    TRANSPORT_FAILURE,
    HttpsWebhookDeliveryAdapter,
)

_NOW = datetime(2026, 8, 4, tzinfo=UTC)
_SIGNING_KEY = "sentinel-key-material-0123456789abcdef"
_REFERENCE = "env:SENTINEL_SIGNING_REFERENCE"


class Resolver:
    def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        return ("8.8.8.8",)


class Secrets:
    def resolve(self, reference: SecretReference) -> SecretMaterial:
        assert str(reference) == _REFERENCE
        return SecretMaterial(_SIGNING_KEY)


@dataclass
class FailingTransport:
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
        raise RuntimeError("sentinel-provider-exception with TLS and signature detail")


def test_signature_and_key_never_reach_result_or_durable_retry_state(tmp_path: Path) -> None:
    endpoint = parse_webhook_endpoints(
        {
            "schema_version": 4,
            "endpoints": {
                "audit": {
                    "url": "https://hooks.example.test/events",
                    "allowed_hostnames": ["hooks.example.test"],
                    "signature_secret": _REFERENCE,
                }
            },
        },
        "workspace",
    )["audit"]
    transport = FailingTransport()
    adapter = HttpsWebhookDeliveryAdapter(endpoint, Resolver(), transport, Secrets())
    outbox = SqliteEventOutbox(tmp_path)
    outbox.append(Event("workspace.initialized", {}))
    outbox.register_consumer("signed")
    service = EventDeliveryService(
        outbox,
        adapter,
        DeliveryRetryProfile(3, (10, 30), 30),
        lambda: _NOW,
    )

    result = service.step("signed")

    assert result.failure_reason == TRANSPORT_FAILURE
    assert len(transport.calls) == 1
    signature = transport.calls[0][2].headers["X-Ansiblectl-Signature"]
    status = outbox.inspect_consumers(now=_NOW)[0]
    surfaces = (repr(result), str(result.to_payload()), repr(status))
    database = (tmp_path / ".ansiblectl/events/outbox.sqlite3").read_bytes()
    for sentinel in (
        _SIGNING_KEY,
        _REFERENCE,
        signature,
        "sentinel-provider-exception",
        "signature detail",
    ):
        assert all(sentinel not in surface for surface in surfaces)
        assert sentinel.encode() not in database

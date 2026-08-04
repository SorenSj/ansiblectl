"""End-to-end redaction tests for signed delivery and durable retry state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

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
from ansiblectl.infrastructure import webhook_delivery as delivery_module
from ansiblectl.infrastructure.event_outbox import SqliteEventOutbox
from ansiblectl.infrastructure.webhook_client_identity import WebhookClientIdentity
from ansiblectl.infrastructure.webhook_delivery import (
    SIGNING_UNAVAILABLE,
    TRANSPORT_FAILURE,
    HttpsWebhookDeliveryAdapter,
)
from ansiblectl.infrastructure.workspace_file_secrets import WorkspaceFileSecretProvider

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


class Clock:
    def now_unix_seconds(self) -> int:
        return 1_786_144_800


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


def test_unsafe_file_reference_never_reaches_result_or_raw_retry_database(
    tmp_path: Path,
) -> None:
    private = tmp_path / ".ansiblectl"
    private.mkdir(mode=0o700)
    private.chmod(0o700)
    secrets = private / "secrets"
    secrets.mkdir(mode=0o700)
    secrets.chmod(0o700)
    key = "SENTINEL_FILE_SIGNING_KEY"
    material = "sentinel-file-material-0123456789abcdef"
    candidate = secrets / key
    candidate.write_text(material, encoding="utf-8")
    candidate.chmod(0o640)
    reference = f"file:{key}"
    endpoint = parse_webhook_endpoints(
        {
            "schema_version": 4,
            "endpoints": {
                "audit": {
                    "url": "https://hooks.example.test/events",
                    "allowed_hostnames": ["hooks.example.test"],
                    "signature_secret": reference,
                }
            },
        },
        "workspace",
    )["audit"]
    outbox = SqliteEventOutbox(tmp_path)
    outbox.append(Event("workspace.initialized", {}))
    outbox.register_consumer("file-signed")
    service = EventDeliveryService(
        outbox,
        HttpsWebhookDeliveryAdapter(
            endpoint, Resolver(), FailingTransport(), WorkspaceFileSecretProvider(tmp_path)
        ),
        DeliveryRetryProfile(3, (10, 30), 30),
        lambda: _NOW,
    )

    result = service.step("file-signed")

    assert result.failure_reason == SIGNING_UNAVAILABLE
    status = outbox.inspect_consumers(now=_NOW)[0]
    database = (tmp_path / ".ansiblectl/events/outbox.sqlite3").read_bytes()
    for sentinel in (key, material, reference, str(candidate), "0o640"):
        assert sentinel not in repr(result)
        assert sentinel not in str(result.to_payload())
        assert sentinel not in repr(status)
        assert sentinel.encode() not in database


def test_v2_timestamp_signature_and_clock_detail_never_reach_durable_state(
    tmp_path: Path,
) -> None:
    endpoint = parse_webhook_endpoints(
        {
            "schema_version": 5,
            "endpoints": {
                "audit": {
                    "url": "https://hooks.example.test/events",
                    "allowed_hostnames": ["hooks.example.test"],
                    "signature_secret": _REFERENCE,
                    "signature_version": 2,
                }
            },
        },
        "workspace",
    )["audit"]
    transport = FailingTransport()
    adapter = HttpsWebhookDeliveryAdapter(endpoint, Resolver(), transport, Secrets(), Clock())
    outbox = SqliteEventOutbox(tmp_path)
    outbox.append(Event("workspace.initialized", {}))
    outbox.register_consumer("timestamp-signed")
    service = EventDeliveryService(
        outbox,
        adapter,
        DeliveryRetryProfile(3, (10, 30), 30),
        lambda: _NOW,
    )

    result = service.step("timestamp-signed")

    assert result.failure_reason == TRANSPORT_FAILURE
    request = transport.calls[0][2]
    timestamp = request.headers["X-Ansiblectl-Timestamp"]
    signature = request.headers["X-Ansiblectl-Signature"]
    status = outbox.inspect_consumers(now=_NOW)[0]
    database = (tmp_path / ".ansiblectl/events/outbox.sqlite3").read_bytes()
    for sentinel in (_SIGNING_KEY, _REFERENCE, timestamp, signature, "signature detail"):
        assert sentinel not in repr(result)
        assert sentinel not in str(result.to_payload())
        assert sentinel not in repr(status)
        assert sentinel.encode() not in database


def test_client_identity_and_tls_metadata_never_reach_public_or_durable_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    certificate_reference = "file:SENTINEL_CLIENT_CERTIFICATE_REFERENCE"
    private_key_reference = "file:SENTINEL_CLIENT_PRIVATE_KEY_REFERENCE"
    certificate_material = "sentinel-client-certificate-material"
    private_key_material = "sentinel-client-private-key-material"
    metadata = "sentinel-subject sentinel-issuer sentinel-serial sentinel-fingerprint"

    class IdentitySecrets:
        def resolve(self, reference: SecretReference) -> SecretMaterial:
            values = {
                certificate_reference: certificate_material,
                private_key_reference: private_key_material,
            }
            return SecretMaterial(values[str(reference)])

    def validate(certificate: SecretMaterial, private_key: SecretMaterial) -> WebhookClientIdentity:
        assert certificate.reveal_for_operation() == certificate_material
        assert private_key.reveal_for_operation() == private_key_material
        return WebhookClientIdentity(b"sentinel-canonical-certificate", b"sentinel-canonical-key")

    @dataclass
    class MetadataFailingTransport:
        request: WebhookRequest | None = None

        def post(
            self,
            endpoint: WebhookEndpoint,
            destination: WebhookDestination,
            request: WebhookRequest,
        ) -> int:
            self.request = request
            raise RuntimeError(f"{metadata} /private/client-key.pem TLS alert")

    monkeypatch.setattr(delivery_module, "validate_webhook_client_identity", validate)
    endpoint = parse_webhook_endpoints(
        {
            "schema_version": 6,
            "endpoints": {
                "audit": {
                    "url": "https://hooks.example.test/events",
                    "allowed_hostnames": ["hooks.example.test"],
                    "client_certificate_secret": certificate_reference,
                    "client_private_key_secret": private_key_reference,
                }
            },
        },
        "workspace",
    )["audit"]
    transport = MetadataFailingTransport()
    outbox = SqliteEventOutbox(tmp_path)
    outbox.append(Event("workspace.initialized", {}))
    outbox.register_consumer("mutual-tls")
    service = EventDeliveryService(
        outbox,
        HttpsWebhookDeliveryAdapter(endpoint, Resolver(), transport, IdentitySecrets()),
        DeliveryRetryProfile(3, (10, 30), 30),
        lambda: _NOW,
    )

    result = service.step("mutual-tls")

    assert result.failure_reason == TRANSPORT_FAILURE
    assert transport.request is not None
    assert "sentinel-canonical" not in repr(transport.request)
    status = outbox.inspect_consumers(now=_NOW)[0]
    surfaces = (repr(result), str(result.to_payload()), repr(status))
    database = (tmp_path / ".ansiblectl/events/outbox.sqlite3").read_bytes()
    for sentinel in (
        certificate_reference,
        private_key_reference,
        certificate_material,
        private_key_material,
        "sentinel-canonical-certificate",
        "sentinel-canonical-key",
        *metadata.split(),
        "/private/client-key.pem",
        "TLS alert",
    ):
        assert all(sentinel not in surface for surface in surfaces)
        assert sentinel.encode() not in database

"""Canonical bounded outbound webhook delivery adapter."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from ansiblectl.domain.durable_events import DurableEventEnvelope
from ansiblectl.domain.event_delivery import DeliveryOutcome
from ansiblectl.domain.secrets import SecretProvider
from ansiblectl.domain.webhooks import (
    MAX_WEBHOOK_PAYLOAD_BYTES,
    WebhookAddressResolver,
    WebhookClock,
    WebhookEndpoint,
    WebhookRequest,
    WebhookTransport,
    resolve_webhook_destination,
)
from ansiblectl.infrastructure.webhook_client_identity import validate_webhook_client_identity

AUTHENTICATION_UNAVAILABLE = "AUTHENTICATION_UNAVAILABLE"
CLIENT_IDENTITY_UNAVAILABLE = "CLIENT_IDENTITY_UNAVAILABLE"
DESTINATION_DENIED = "DESTINATION_DENIED"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
REMOTE_REJECTED = "REMOTE_REJECTED"
REMOTE_RETRYABLE = "REMOTE_RETRYABLE"
SIGNING_UNAVAILABLE = "SIGNING_UNAVAILABLE"
TRANSPORT_FAILURE = "TRANSPORT_FAILURE"
WEBHOOK_SIGNATURE_DOMAIN = b"ansiblectl-webhook-signature-v1\n"
WEBHOOK_SIGNATURE_V2_DOMAIN = b"ansiblectl-webhook-signature-v2\n"
MIN_WEBHOOK_SIGNING_KEY_BYTES = 32
MAX_WEBHOOK_SIGNING_KEY_BYTES = 256


@dataclass(frozen=True)
class HttpsWebhookDeliveryAdapter:
    """Map one immutable envelope to at most one bounded transport attempt."""

    endpoint: WebhookEndpoint
    resolver: WebhookAddressResolver
    transport: WebhookTransport
    secrets: SecretProvider | None = None
    clock: WebhookClock | None = None

    def deliver(self, envelope: DurableEventEnvelope) -> DeliveryOutcome:
        body = envelope.to_canonical_bytes()
        if len(body) > MAX_WEBHOOK_PAYLOAD_BYTES:
            return DeliveryOutcome.failure(PAYLOAD_TOO_LARGE)
        bearer = None
        if self.endpoint.bearer_secret is not None:
            if self.secrets is None:
                return DeliveryOutcome.failure(AUTHENTICATION_UNAVAILABLE)
            try:
                bearer = self.secrets.resolve(self.endpoint.bearer_secret)
                revealed = bearer.reveal_for_operation()
                if not revealed or any(char in revealed for char in "\r\n"):
                    return DeliveryOutcome.failure(AUTHENTICATION_UNAVAILABLE)
            except Exception:
                return DeliveryOutcome.failure(AUTHENTICATION_UNAVAILABLE)
        signing_key = None
        if self.endpoint.signature_secret is not None:
            if self.secrets is None:
                return DeliveryOutcome.failure(SIGNING_UNAVAILABLE)
            try:
                signing_material = self.secrets.resolve(self.endpoint.signature_secret)
                signing_value = signing_material.reveal_for_operation()
                signing_key = signing_value.encode("utf-8")
                if not MIN_WEBHOOK_SIGNING_KEY_BYTES <= len(
                    signing_key
                ) <= MAX_WEBHOOK_SIGNING_KEY_BYTES or any(
                    ord(char) < 32 or 127 <= ord(char) <= 159 for char in signing_value
                ):
                    return DeliveryOutcome.failure(SIGNING_UNAVAILABLE)
            except Exception:
                return DeliveryOutcome.failure(SIGNING_UNAVAILABLE)
        client_identity = None
        if self.endpoint.client_certificate_secret is not None:
            if self.secrets is None or self.endpoint.client_private_key_secret is None:
                return DeliveryOutcome.failure(CLIENT_IDENTITY_UNAVAILABLE)
            try:
                certificate = self.secrets.resolve(self.endpoint.client_certificate_secret)
                private_key = self.secrets.resolve(self.endpoint.client_private_key_secret)
                client_identity = validate_webhook_client_identity(certificate, private_key)
            except Exception:
                return DeliveryOutcome.failure(CLIENT_IDENTITY_UNAVAILABLE)
        signature = None
        timestamp = None
        if signing_key is not None:
            try:
                if self.endpoint.signature_version == 2:
                    if self.clock is None:
                        return DeliveryOutcome.failure(SIGNING_UNAVAILABLE)
                    timestamp_value = self.clock.now_unix_seconds()
                    if (
                        not isinstance(timestamp_value, int)
                        or isinstance(timestamp_value, bool)
                        or not 0 <= timestamp_value <= 253_402_300_799
                    ):
                        return DeliveryOutcome.failure(SIGNING_UNAVAILABLE)
                    timestamp = str(timestamp_value)
                    signed = WEBHOOK_SIGNATURE_V2_DOMAIN + timestamp.encode("ascii") + b"\n" + body
                    signature = f"v2={hmac.new(signing_key, signed, hashlib.sha256).hexdigest()}"
                else:
                    digest = hmac.new(
                        signing_key, WEBHOOK_SIGNATURE_DOMAIN + body, hashlib.sha256
                    ).hexdigest()
                    signature = f"v1={digest}"
            except Exception:
                return DeliveryOutcome.failure(SIGNING_UNAVAILABLE)
        try:
            destination = resolve_webhook_destination(self.endpoint, self.resolver)
        except Exception:
            return DeliveryOutcome.failure(DESTINATION_DENIED)
        headers = {
            "Content-Type": "application/json",
            "Idempotency-Key": envelope.event_id,
            "User-Agent": "ansiblectl-webhook/1",
            "X-Ansiblectl-Event-Id": envelope.event_id,
            "X-Ansiblectl-Event-Sequence": str(envelope.sequence),
        }
        if signature is not None:
            headers["X-Ansiblectl-Signature"] = signature
        if timestamp is not None:
            headers["X-Ansiblectl-Timestamp"] = timestamp
        request = WebhookRequest(body, headers, bearer, client_identity)
        try:
            status = self.transport.post(self.endpoint, destination, request)
        except Exception:
            return DeliveryOutcome.failure(TRANSPORT_FAILURE)
        if not isinstance(status, int) or isinstance(status, bool) or not 100 <= status <= 599:
            return DeliveryOutcome.failure(TRANSPORT_FAILURE)
        if 200 <= status <= 299:
            return DeliveryOutcome.success()
        if status in {408, 425, 429} or 500 <= status <= 599:
            return DeliveryOutcome.failure(REMOTE_RETRYABLE)
        return DeliveryOutcome.failure(REMOTE_REJECTED)


__all__ = [
    "AUTHENTICATION_UNAVAILABLE",
    "CLIENT_IDENTITY_UNAVAILABLE",
    "DESTINATION_DENIED",
    "HttpsWebhookDeliveryAdapter",
    "PAYLOAD_TOO_LARGE",
    "REMOTE_REJECTED",
    "REMOTE_RETRYABLE",
    "SIGNING_UNAVAILABLE",
    "TRANSPORT_FAILURE",
    "WEBHOOK_SIGNATURE_DOMAIN",
    "WEBHOOK_SIGNATURE_V2_DOMAIN",
]
